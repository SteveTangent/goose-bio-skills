#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded descriptive Kaplan-Meier report from a subject-level TSV."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


VERSION = "0.7.0"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_SUBJECTS = 100_000
MAX_GROUPS = 20
MAX_TOKEN_CHARS = 256
MAX_NUMBER_CHARS = 128
MAX_TIME_ADJUSTED_EXPONENT = 128
DECIMAL_NUMBER = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z"
)
UNGROUPED_HEADER = ["subject_id", "time", "event"]
GROUPED_HEADER = [*UNGROUPED_HEADER, "group"]


class InputError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("input validation failed")
        self.issues = issues


def issue(
    code: str,
    *,
    role: str | None = None,
    line: int | None = None,
    field: str | None = None,
    value: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code}
    if role is not None:
        result["role"] = role
    if line is not None:
        result["line"] = line
    if field is not None:
        result["field"] = field
    if value is not None:
        result["value"] = value
    return result


def validate_token(value: str, *, line: int, field: str) -> None:
    if not value:
        raise InputError([issue("empty-value", role="subjects", line=line, field=field)])
    if value != value.strip():
        raise InputError([
            issue("surrounding-whitespace", role="subjects", line=line, field=field)
        ])
    if len(value) > MAX_TOKEN_CHARS:
        raise InputError([issue("value-too-long", role="subjects", line=line, field=field)])
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputError([issue("control-character", role="subjects", line=line, field=field)])


def read_local_file(
    path: Path, *, root: Path | None = None
) -> tuple[bytes, str]:
    """Read one stable regular file without following symlink components."""
    supplied = Path(path)
    if ".." in supplied.parts:
        raise InputError([issue("parent-traversal", role="subjects")])
    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    parent_fd = -1
    try:
        root_state = os.lstat(lexical_root)
        if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
            raise InputError([issue("unsafe-working-directory", role="subjects")])
        candidate = Path(os.path.abspath(
            supplied if supplied.is_absolute() else lexical_root / supplied
        ))
        try:
            relative = candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise InputError([
                issue("path-outside-working-directory", role="subjects")
            ]) from exc
        if not relative.parts:
            raise InputError([issue("input-not-regular-file", role="subjects")])

        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_fd = os.open(lexical_root, directory_flags)
        opened_root = os.fstat(parent_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (
            root_state.st_dev,
            root_state.st_ino,
        ):
            raise InputError([issue("unsafe-working-directory", role="subjects")])
        for part in relative.parts[:-1]:
            try:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise InputError([issue("input-parent-symlink", role="subjects")]) from exc
            os.close(parent_fd)
            parent_fd = child_fd

        name = relative.parts[-1]
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise InputError([issue("input-not-regular-file", role="subjects")])
        if before.st_size > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large", role="subjects")])

        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise InputError([issue("input-not-regular-file", role="subjects")])
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise InputError([issue("input-changed-during-read", role="subjects")])
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read(MAX_INPUT_BYTES + 1)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large", role="subjects")])
        if any(getattr(opened, key) != getattr(after_open, key) for key in stable):
            raise InputError([issue("input-changed-during-read", role="subjects")])
        if any(getattr(after_open, key) != getattr(after_path, key) for key in stable):
            raise InputError([issue("input-changed-during-read", role="subjects")])
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError([issue("input-not-utf8", role="subjects")]) from exc
        if "\x00" in text:
            raise InputError([issue("nul-byte-in-input", role="subjects")])
        return payload, text
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise InputError([issue("input-unreadable", role="subjects")]) from exc
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def parse_subjects(text: str) -> dict[str, Any]:
    try:
        reader = csv.reader(io.StringIO(text), delimiter="\t", strict=True)
        header = next(reader)
    except StopIteration as exc:
        raise InputError([issue("missing-header", role="subjects")]) from exc
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv", role="subjects")]) from exc

    if header not in (UNGROUPED_HEADER, GROUPED_HEADER):
        raise InputError([issue(
            "invalid-header",
            role="subjects",
            value={"allowed": [UNGROUPED_HEADER, GROUPED_HEADER], "observed": header},
        )])
    grouped = header == GROUPED_HEADER
    records: list[dict[str, Any]] = []
    subject_ids: set[str] = set()
    groups: set[str] = set()
    try:
        for row_number, row in enumerate(reader, start=1):
            line = row_number + 1
            if row_number > MAX_SUBJECTS:
                raise InputError([issue("too-many-subjects", role="subjects", line=line)])
            if len(row) != len(header):
                raise InputError([issue("ragged-row", role="subjects", line=line)])
            subject_id, raw_time, raw_event = row[:3]
            validate_token(subject_id, line=line, field="subject_id")
            if subject_id in subject_ids:
                raise InputError([issue(
                    "duplicate-subject-id",
                    role="subjects",
                    line=line,
                    field="subject_id",
                    value=subject_id,
                )])
            subject_ids.add(subject_id)

            validate_token(raw_time, line=line, field="time")
            if len(raw_time) > MAX_NUMBER_CHARS:
                raise InputError([issue("value-too-long", role="subjects", line=line,
                                        field="time")])
            if DECIMAL_NUMBER.fullmatch(raw_time) is None:
                raise InputError([issue("invalid-time", role="subjects", line=line,
                                        field="time", value=raw_time)])
            try:
                time = Decimal(raw_time)
            except InvalidOperation as exc:
                raise InputError([issue("invalid-time", role="subjects", line=line,
                                        field="time", value=raw_time)]) from exc
            if not time.is_finite():
                raise InputError([issue("nonfinite-time", role="subjects", line=line,
                                        field="time", value=raw_time)])
            if time < 0:
                raise InputError([issue("negative-time", role="subjects", line=line,
                                        field="time", value=raw_time)])
            if time == 0:
                time = Decimal(0)
            elif abs(time.adjusted()) > MAX_TIME_ADJUSTED_EXPONENT:
                raise InputError([issue("time-out-of-range", role="subjects", line=line,
                                        field="time", value=raw_time)])

            if raw_event not in ("0", "1"):
                raise InputError([issue("invalid-event", role="subjects", line=line,
                                        field="event", value=raw_event)])
            group: str | None = None
            if grouped:
                group = row[3]
                validate_token(group, line=line, field="group")
                groups.add(group)
                if len(groups) > MAX_GROUPS:
                    raise InputError([issue("too-many-groups", role="subjects", line=line)])
            records.append({
                "subject_id": subject_id,
                "time": time,
                "event": int(raw_event),
                "group": group,
            })
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv", role="subjects")]) from exc
    if not records:
        raise InputError([issue("no-subjects", role="subjects")])
    return {"records": records, "grouped": grouped, "groups": sorted(groups)}


def canonical_time(value: Decimal) -> int | str:
    if value == value.to_integral_value():
        return int(value)
    return format(value.normalize(), "f")


def kaplan_meier(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[Decimal, list[int]] = {}
    for record in records:
        event_count, censor_count = counts.setdefault(record["time"], [0, 0])
        if record["event"]:
            event_count += 1
        else:
            censor_count += 1
        counts[record["time"]] = [event_count, censor_count]

    at_risk = len(records)
    survival = 1.0
    median_time: Decimal | None = None
    curve: list[dict[str, Any]] = []
    total_events = 0
    for time in sorted(counts):
        events, censored = counts[time]
        total_events += events
        if events:
            survival *= (at_risk - events) / at_risk
        if median_time is None and survival <= 0.5:
            median_time = time
        curve.append({
            "time": canonical_time(time),
            "n_at_risk": at_risk,
            "events": events,
            "censored": censored,
            "survival_probability": survival,
        })
        at_risk -= events + censored
    if at_risk != 0:
        raise RuntimeError("internal risk-set accounting error")
    return {
        "subject_count": len(records),
        "event_count": total_events,
        "censor_count": len(records) - total_events,
        "median": {
            "status": "estimated" if median_time is not None else "not-reached",
            "time": canonical_time(median_time) if median_time is not None else None,
        },
        "curve": curve,
    }


def analyze(payload: bytes, text: str) -> dict[str, Any]:
    parsed = parse_subjects(text)
    records = parsed["records"]
    groups = parsed["groups"]
    group_curves = [
        {
            "group": group,
            **kaplan_meier([record for record in records if record["group"] == group]),
        }
        for group in groups
    ]
    return {
        "schema_version": "1.0",
        "analysis": {
            "method": "kaplan-meier-product-limit",
            "same-time_order": "events-before-censor-removal",
            "time_representation": "exact-decimal; integral-json-number-or-canonical-decimal-string",
            "group_comparison": "descriptive-curves-only",
            "decisions_or_thresholds_applied": False,
        },
        "input": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "header": GROUPED_HEADER if parsed["grouped"] else UNGROUPED_HEADER,
            "group_column_present": parsed["grouped"],
            "subject_count": len(records),
            "group_count": len(groups),
        },
        "overall": kaplan_meier(records),
        "groups": group_curves,
        "limitations": [
            "Endpoint, time-origin, time-unit, censoring, and group semantics are caller declarations.",
            "Kaplan-Meier estimation relies on assumptions including non-informative censoring that this helper cannot verify.",
            "No log-rank, confidence interval, Cox or parametric model, delayed-entry, recurrent-event, competing-risk, interval-censoring, time-varying, or multiplicity analysis was performed.",
        ],
    }


def output_target(
    path: Path, root: Path | None = None
) -> tuple[Path, Path, tuple[str, ...], os.stat_result]:
    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    root_state = os.lstat(lexical_root)
    if stat.S_ISLNK(root_state.st_mode):
        raise PermissionError(f"output root is a symlink: {lexical_root}")
    if not stat.S_ISDIR(root_state.st_mode):
        raise NotADirectoryError(lexical_root)
    if ".." in path.parts:
        raise PermissionError(f"output path contains parent traversal: {path}")
    candidate = Path(os.path.abspath(path if path.is_absolute() else lexical_root / path))
    try:
        relative = candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise PermissionError(f"output is outside the allowed root: {candidate}") from exc
    if not relative.parts:
        raise IsADirectoryError(candidate)
    return lexical_root, candidate, relative.parts, root_state


def open_output_parent(path: Path, root: Path | None = None) -> tuple[Path, int, str]:
    lexical_root, candidate, parts, root_state = output_target(path, root)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(lexical_root, flags)
    opened_root = os.fstat(descriptor)
    if (opened_root.st_dev, opened_root.st_ino) != (
        root_state.st_dev,
        root_state.st_ino,
    ):
        os.close(descriptor)
        raise PermissionError(f"output root changed or is unsafe: {lexical_root}")
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                raise FileNotFoundError(f"output parent does not exist: {candidate.parent}") from exc
            except OSError as exc:
                raise PermissionError(f"output parent is unsafe: {candidate.parent}") from exc
            os.close(descriptor)
            descriptor = child
        try:
            os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(candidate)
        return candidate, descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def unlink_owned_at(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def write_new(path: Path, text: str, *, root: Path | None = None) -> Path:
    target, directory_fd, target_name = open_output_parent(path, root)
    temporary_name = f".{target_name}.tmp-{secrets.token_hex(12)}"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    identity: tuple[int, int] | None = None
    published = False
    cleanup_failures: list[str] = []
    try:
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="", closefd=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(
                temporary_name,
                target_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise FileExistsError(target) from exc
        published = True
        if not unlink_owned_at(temporary_name, directory_fd, identity):
            raise OSError("staged output identity changed before cleanup")
        os.fsync(directory_fd)
        final_state = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        if (final_state.st_dev, final_state.st_ino) != identity:
            raise OSError("published output identity changed before completion")
    except BaseException as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            if published:
                try:
                    if not unlink_owned_at(target_name, directory_fd, identity):
                        cleanup_failures.append("published output identity changed")
                except OSError as cleanup_exc:
                    cleanup_failures.append(
                        f"published output cleanup failed: {cleanup_exc.__class__.__name__}"
                    )
            try:
                if not unlink_owned_at(temporary_name, directory_fd, identity):
                    cleanup_failures.append("staged output identity changed")
            except OSError as cleanup_exc:
                cleanup_failures.append(
                    f"staged output cleanup failed: {cleanup_exc.__class__.__name__}"
                )
            try:
                os.fsync(directory_fd)
            except OSError as cleanup_exc:
                cleanup_failures.append(
                    f"directory rollback sync failed: {cleanup_exc.__class__.__name__}"
                )
        if cleanup_failures:
            raise OSError("; ".join(cleanup_failures)) from exc
        raise
    finally:
        os.close(directory_fd)
    return target


def self_test() -> None:
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        if not condition:
            raise RuntimeError(message)
        checks += 1

    def expect_issue(code: str, action: Callable[[], Any]) -> None:
        nonlocal checks
        try:
            action()
        except InputError as exc:
            if not exc.issues or exc.issues[0]["code"] != code:
                raise RuntimeError(f"expected {code}, got {exc.issues}") from exc
        else:
            raise AssertionError(f"{code} input was accepted")
        checks += 1

    grouped_text = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t1\t1\tA\nA2\t2\t0\tA\nA3\t3\t1\tA\n"
        "B1\t1\t0\tB\nB2\t2\t1\tB\nB3\t4\t1\tB\n"
    )
    report = analyze(grouped_text.encode(), grouped_text)
    check(report["input"]["subject_count"] == 6, "subject count differs")
    check(report["input"]["group_count"] == 2, "group count differs")
    overall = report["overall"]
    check(overall["event_count"] == 4 and overall["censor_count"] == 2,
          "overall outcome counts differ")
    check(overall["median"] == {"status": "estimated", "time": 3.0},
          "overall median differs")
    check(overall["curve"][0] == {
        "time": 1.0,
        "n_at_risk": 6,
        "events": 1,
        "censored": 1,
        "survival_probability": 5 / 6,
    }, "same-time event/censor step differs")
    groups = {entry["group"]: entry for entry in report["groups"]}
    check(groups["A"]["median"]["time"] == 3.0, "group A median differs")
    check(groups["B"]["median"]["time"] == 2.0, "group B median differs")
    repeat = analyze(grouped_text.encode(), grouped_text)
    check(json.dumps(report, allow_nan=False, sort_keys=True) ==
          json.dumps(repeat, allow_nan=False, sort_keys=True), "determinism differs")

    ungrouped_text = "subject_id\ttime\tevent\nS1\t1\t0\nS2\t2\t0\n"
    ungrouped = analyze(ungrouped_text.encode(), ungrouped_text)
    check(ungrouped["overall"]["median"] == {
        "status": "not-reached", "time": None,
    }, "all-censored median differs")

    exact_times = (
        "subject_id\ttime\tevent\n"
        "C\t9007199254740992\t0\n"
        "E\t9007199254740993\t1\n"
    )
    exact_curve = analyze(exact_times.encode(), exact_times)["overall"]["curve"]
    check(
        exact_curve == [
            {
                "time": 9007199254740992,
                "n_at_risk": 2,
                "events": 0,
                "censored": 1,
                "survival_probability": 1.0,
            },
            {
                "time": 9007199254740993,
                "n_at_risk": 1,
                "events": 1,
                "censored": 0,
                "survival_probability": 0.0,
            },
        ],
        "distinct exact times collapsed",
    )

    expect_issue("invalid-header", lambda: parse_subjects(
        "id\ttime\tevent\nS1\t1\t1\n"))
    expect_issue("duplicate-subject-id", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t1\t1\nS1\t2\t0\n"))
    expect_issue("negative-time", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t-1\t1\n"))
    expect_issue("invalid-time", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\tNaN\t1\n"))
    expect_issue("time-out-of-range", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t1e999999\t1\n"))
    expect_issue("invalid-event", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t1\tdead\n"))
    expect_issue("empty-value", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\t1\t\n"))
    expect_issue("ragged-row", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t1\n"))
    expect_issue("no-subjects", lambda: parse_subjects(
        "subject_id\ttime\tevent\n"))

    with tempfile.TemporaryDirectory(prefix="km-selftest-") as temporary_name:
        root = Path(temporary_name)
        regular = root / "subjects.tsv"
        regular.write_text(grouped_text, encoding="utf-8")
        payload, text = read_local_file(regular, root=root)
        check(payload == grouped_text.encode() and text == grouped_text,
              "regular input read differs")
        linked = root / "linked.tsv"
        linked.symlink_to(regular)
        expect_issue("input-not-regular-file", lambda: read_local_file(linked, root=root))
        expect_issue("parent-traversal", lambda: read_local_file(
            Path("..") / "outside.tsv", root=root))

        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "subjects.tsv").write_text(grouped_text, encoding="utf-8")
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect_issue("input-parent-symlink", lambda: read_local_file(
            linked_input_parent / "subjects.tsv", root=root))

        output = root / "report.json"
        write_new(output, "{}\n", root=root)
        try:
            write_new(output, "replacement\n", root=root)
        except FileExistsError:
            check(output.read_text(encoding="utf-8") == "{}\n",
                  "existing output was replaced")
        else:
            raise AssertionError("existing output was replaced")
        try:
            write_new(Path("..") / "escape.json", "{}\n", root=root)
        except PermissionError:
            checks += 1
        else:
            raise AssertionError("parent traversal output was accepted")

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        try:
            write_new(Path("linked-parent") / "report.json", "{}\n", root=root)
        except PermissionError:
            checks += 1
        else:
            raise AssertionError("symlinked output parent was accepted")

        rollback_output = root / "rollback-report.json"
        original_fsync = os.fsync
        failed_directory_sync = False

        def fail_first_directory_sync(descriptor: int) -> None:
            nonlocal failed_directory_sync
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed_directory_sync:
                failed_directory_sync = True
                raise OSError("injected directory sync failure")
            original_fsync(descriptor)

        os.fsync = fail_first_directory_sync
        try:
            try:
                write_new(rollback_output, "{}\n", root=root)
            except OSError:
                check(not rollback_output.exists(),
                      "failed publication left the final output")
                check(not list(root.glob(".rollback-report.json.tmp-*")),
                      "failed publication left a staged output")
            else:
                raise AssertionError("directory sync failure was accepted")
        finally:
            os.fsync = original_fsync

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION},
                     sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    if arguments.input is None or arguments.output is None:
        parser().error("--input and --output are required for execution")
    try:
        payload, text = read_local_file(arguments.input)
        report = analyze(payload, text)
        rendered = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
        write_new(arguments.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "groups": report["input"]["group_count"],
            "output": str(arguments.output),
            "status": "completed",
            "subjects": report["input"]["subject_count"],
        }, sort_keys=True))
        return 0
    except InputError as exc:
        print(json.dumps({"analysis_performed": False, "issues": exc.issues,
                          "status": "invalid-input"}, sort_keys=True), file=sys.stderr)
        return 2
    except (FileExistsError, FileNotFoundError, IsADirectoryError,
            NotADirectoryError, PermissionError) as exc:
        print(json.dumps({"analysis_performed": False, "error": str(exc),
                          "status": "invalid-output"}, sort_keys=True), file=sys.stderr)
        return 3
    except OSError as exc:
        print(json.dumps({"analysis_performed": False, "error": str(exc),
                          "status": "io-error"}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
