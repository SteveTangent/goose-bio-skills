#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded two-group Mantel-Cox log-rank report from a TSV."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import io
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


VERSION = "0.9.0"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_SUBJECTS = 100_000
MAX_TOKEN_CHARS = 256
MAX_NUMBER_CHARS = 128
MAX_TIME_ADJUSTED_EXPONENT = 128
DECIMAL_NUMBER = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z"
)
HEADER = ["subject_id", "time", "event", "group"]


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
        raise InputError([
            issue("value-too-long", role="subjects", line=line, field=field)
        ])
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputError([
            issue("control-character", role="subjects", line=line, field=field)
        ])


def read_local_file(path: Path, *, root: Path | None = None) -> tuple[bytes, str]:
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
                raise InputError([
                    issue("input-parent-symlink", role="subjects")
                ]) from exc
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
                raise InputError([
                    issue("input-changed-during-read", role="subjects")
                ])
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
    if header != HEADER:
        raise InputError([issue(
            "invalid-header",
            role="subjects",
            value={"allowed": HEADER, "observed": header},
        )])

    records: list[dict[str, Any]] = []
    subject_ids: set[str] = set()
    groups: set[str] = set()
    try:
        for row_number, row in enumerate(reader, start=1):
            line = row_number + 1
            if row_number > MAX_SUBJECTS:
                raise InputError([
                    issue("too-many-subjects", role="subjects", line=line)
                ])
            if len(row) != len(HEADER):
                raise InputError([issue("ragged-row", role="subjects", line=line)])
            subject_id, raw_time, raw_event, group = row
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
                raise InputError([
                    issue("value-too-long", role="subjects", line=line, field="time")
                ])
            if DECIMAL_NUMBER.fullmatch(raw_time) is None:
                raise InputError([issue(
                    "invalid-time", role="subjects", line=line,
                    field="time", value=raw_time,
                )])
            try:
                time = Decimal(raw_time)
            except InvalidOperation as exc:
                raise InputError([issue(
                    "invalid-time", role="subjects", line=line,
                    field="time", value=raw_time,
                )]) from exc
            if not time.is_finite():
                raise InputError([issue(
                    "nonfinite-time", role="subjects", line=line,
                    field="time", value=raw_time,
                )])
            if time < 0:
                raise InputError([issue(
                    "negative-time", role="subjects", line=line,
                    field="time", value=raw_time,
                )])
            if time == 0:
                time = Decimal(0)
            elif abs(time.adjusted()) > MAX_TIME_ADJUSTED_EXPONENT:
                raise InputError([issue(
                    "time-out-of-range", role="subjects", line=line,
                    field="time", value=raw_time,
                )])

            if raw_event not in ("0", "1"):
                raise InputError([issue(
                    "invalid-event", role="subjects", line=line,
                    field="event", value=raw_event,
                )])
            validate_token(group, line=line, field="group")
            groups.add(group)
            if len(groups) > 2:
                raise InputError([issue(
                    "group-count-not-two", role="subjects", line=line,
                    field="group", value={"observed_at_least": len(groups)},
                )])
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
    if len(groups) != 2:
        raise InputError([issue(
            "group-count-not-two", role="subjects", value={"observed": len(groups)},
        )])
    return {"records": records, "groups": sorted(groups)}


def canonical_time(value: Decimal) -> int | str:
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f").rstrip("0").rstrip(".")


def rational(value: Fraction) -> dict[str, int | float]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def log_rank(records: list[dict[str, Any]], groups: list[str]) -> dict[str, Any]:
    index = {groups[0]: 0, groups[1]: 1}
    # [events A, censors A, events B, censors B]
    counts: dict[Decimal, list[int]] = {}
    group_subjects = [0, 0]
    group_events = [0, 0]
    for record in records:
        group_index = index[record["group"]]
        group_subjects[group_index] += 1
        bucket = counts.setdefault(record["time"], [0, 0, 0, 0])
        offset = 2 * group_index + (0 if record["event"] else 1)
        bucket[offset] += 1
        if record["event"]:
            group_events[group_index] += 1

    at_risk = group_subjects.copy()
    observed_a = 0
    expected_a = Fraction(0)
    total_variance = Fraction(0)
    event_times: list[dict[str, Any]] = []
    for time in sorted(counts):
        events_a, censors_a, events_b, censors_b = counts[time]
        total_events = events_a + events_b
        if total_events:
            total_at_risk = at_risk[0] + at_risk[1]
            expected = Fraction(total_events * at_risk[0], total_at_risk)
            variance = Fraction(0)
            if total_at_risk > 1:
                variance = Fraction(
                    at_risk[0] * at_risk[1] * total_events
                    * (total_at_risk - total_events),
                    total_at_risk * total_at_risk * (total_at_risk - 1),
                )
            difference = Fraction(events_a) - expected
            observed_a += events_a
            expected_a += expected
            total_variance += variance
            event_times.append({
                "time": canonical_time(time),
                "risk_set": {
                    "group_a": at_risk[0],
                    "group_b": at_risk[1],
                    "total": total_at_risk,
                },
                "events": {
                    "group_a": events_a,
                    "group_b": events_b,
                    "total": total_events,
                },
                "same_time_censors": {
                    "group_a": censors_a,
                    "group_b": censors_b,
                    "total": censors_a + censors_b,
                },
                "expected_group_a_events": rational(expected),
                "observed_minus_expected": {
                    "group_a": rational(difference),
                    "group_b": rational(-difference),
                },
                "variance_group_a": rational(variance),
            })
        at_risk[0] -= events_a + censors_a
        at_risk[1] -= events_b + censors_b
    if at_risk != [0, 0]:
        raise RuntimeError("internal risk-set accounting error")

    total_events = group_events[0] + group_events[1]
    expected_b = Fraction(total_events) - expected_a
    difference_a = Fraction(observed_a) - expected_a
    difference_b = Fraction(group_events[1]) - expected_b
    if difference_b != -difference_a:
        raise RuntimeError("internal observed-minus-expected accounting error")

    if total_variance > 0:
        chi_square = difference_a * difference_a / total_variance
        p_value = math.erfc(math.sqrt(float(chi_square) / 2.0))
        comparison = {
            "status": "estimated",
            "reason": None,
            "chi_square": rational(chi_square),
            "degrees_of_freedom": 1,
            "p_value": p_value if p_value > 0.0 else None,
            "p_value_status": "estimated" if p_value > 0.0 else "underflow",
        }
    else:
        comparison = {
            "status": "not-estimable",
            "reason": "zero-total-variance",
            "chi_square": None,
            "degrees_of_freedom": 1,
            "p_value": None,
            "p_value_status": "not-estimable",
        }

    return {
        "event_times": event_times,
        "totals": {
            "subjects": {
                "group_a": group_subjects[0],
                "group_b": group_subjects[1],
                "total": sum(group_subjects),
            },
            "observed_events": {
                "group_a": group_events[0],
                "group_b": group_events[1],
                "total": total_events,
            },
            "censors": {
                "group_a": group_subjects[0] - group_events[0],
                "group_b": group_subjects[1] - group_events[1],
                "total": len(records) - total_events,
            },
            "expected_events": {
                "group_a": rational(expected_a),
                "group_b": rational(expected_b),
            },
            "observed_minus_expected": {
                "group_a": rational(difference_a),
                "group_b": rational(difference_b),
            },
            "variance_group_a": rational(total_variance),
        },
        "comparison": comparison,
    }


def analyze(payload: bytes, text: str) -> dict[str, Any]:
    parsed = parse_subjects(text)
    groups = parsed["groups"]
    result = log_rank(parsed["records"], groups)
    return {
        "schema_version": "1.0",
        "analysis": {
            "method": "mantel-cox-log-rank",
            "alternative": "two-sided",
            "degrees_of_freedom": 1,
            "correction": "none",
            "same_time_order": "events-before-censor-removal",
            "time_representation": (
                "exact-decimal; integral-json-number-or-canonical-decimal-string"
            ),
            "group_order": "lexicographic-label-order-for-reporting-only",
            "group_a": groups[0],
            "group_b": groups[1],
            "decisions_or_thresholds_applied": False,
        },
        "input": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "header": HEADER,
            "subject_count": len(parsed["records"]),
            "group_count": 2,
        },
        **result,
        "limitations": [
            "Endpoint, time-origin, time-unit, censoring, and group semantics are caller declarations.",
            "The log-rank comparison relies on assumptions including non-informative censoring that this helper cannot verify.",
            "No Kaplan-Meier curve or median, confidence interval, hazard ratio, Cox or parametric model, delayed-entry, recurrent-event, competing-risk, interval-censoring, time-varying, stratified, weighted, multiplicity, significance-decision, causal, or clinical analysis was performed.",
            "The p-value uses platform libm through Python math.erfc; its last binary floating-point digit is not a cross-platform guarantee.",
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
                raise FileNotFoundError(
                    f"output parent does not exist: {candidate.parent}"
                ) from exc
            except OSError as exc:
                raise PermissionError(
                    f"output parent is unsafe: {candidate.parent}"
                ) from exc
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
                        "published output cleanup failed: "
                        f"{cleanup_exc.__class__.__name__}"
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

    fixture = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t1\t1\tA\nA2\t2\t1\tA\nA3\t2\t0\tA\n"
        "B1\t2\t1\tB\nB2\t3\t0\tB\nB3\t4\t0\tB\n"
    )
    report = analyze(fixture.encode(), fixture)
    check(report["analysis"]["group_a"] == "A" and
          report["analysis"]["group_b"] == "B", "group order differs")
    check(len(report["event_times"]) == 2, "event-time count differs")
    first, second = report["event_times"]
    check(first["time"] == 1 and first["risk_set"] == {
        "group_a": 3, "group_b": 3, "total": 6,
    }, "first risk set differs")
    check(first["events"] == {
        "group_a": 1, "group_b": 0, "total": 1,
    }, "first event counts differ")
    check(first["expected_group_a_events"] == rational(Fraction(1, 2)),
          "first expectation differs")
    check(first["observed_minus_expected"] == {
        "group_a": rational(Fraction(1, 2)),
        "group_b": rational(Fraction(-1, 2)),
    }, "first O-E differs")
    check(first["variance_group_a"] == rational(Fraction(1, 4)),
          "first variance differs")
    check(second["time"] == 2 and second["risk_set"] == {
        "group_a": 2, "group_b": 3, "total": 5,
    }, "second risk set differs")
    check(second["events"] == {
        "group_a": 1, "group_b": 1, "total": 2,
    }, "second event counts differ")
    check(second["same_time_censors"] == {
        "group_a": 1, "group_b": 0, "total": 1,
    }, "same-time censor accounting differs")
    check(second["expected_group_a_events"] == rational(Fraction(4, 5)),
          "second expectation differs")
    check(second["observed_minus_expected"] == {
        "group_a": rational(Fraction(1, 5)),
        "group_b": rational(Fraction(-1, 5)),
    }, "second O-E differs")
    check(second["variance_group_a"] == rational(Fraction(9, 25)),
          "second variance differs")
    totals = report["totals"]
    check(totals["observed_events"] == {
        "group_a": 2, "group_b": 1, "total": 3,
    }, "observed totals differ")
    check(totals["expected_events"]["group_a"] == rational(Fraction(13, 10)) and
          totals["expected_events"]["group_b"] == rational(Fraction(17, 10)),
          "expected totals differ")
    check(totals["observed_minus_expected"]["group_a"] ==
          rational(Fraction(7, 10)) and
          totals["observed_minus_expected"]["group_b"] ==
          rational(Fraction(-7, 10)), "O-E totals differ")
    check(totals["variance_group_a"] == rational(Fraction(61, 100)),
          "total variance differs")
    comparison = report["comparison"]
    check(comparison["status"] == "estimated" and
          comparison["chi_square"] == rational(Fraction(49, 61)),
          "chi-square differs")
    check(abs(comparison["p_value"] - 0.3701148999172464) < 1e-15,
          "p-value differs from the hand-calculated oracle")
    check(comparison["p_value_status"] == "estimated",
          "p-value status differs")
    check(report["analysis"]["decisions_or_thresholds_applied"] is False,
          "decision boundary differs")

    repeat = analyze(fixture.encode(), fixture)
    check(json.dumps(report, allow_nan=False, sort_keys=True) ==
          json.dumps(repeat, allow_nan=False, sort_keys=True),
          "determinism differs")
    fixture_lines = fixture.splitlines()
    reversed_fixture = fixture_lines[0] + "\n" + "\n".join(
        reversed(fixture_lines[1:])
    ) + "\n"
    reversed_report = analyze(reversed_fixture.encode(), reversed_fixture)
    check(report["event_times"] == reversed_report["event_times"] and
          report["totals"] == reversed_report["totals"] and
          report["comparison"] == reversed_report["comparison"],
          "row-order invariant results differ")

    exact_times = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t9007199254740993\t1\tA\n"
        "A2\t9007199254740992\t0\tA\n"
        "B1\t9007199254740993\t0\tB\n"
        "B2\t9007199254740994\t1\tB\n"
    )
    exact_event_times = analyze(exact_times.encode(), exact_times)["event_times"]
    check([row["time"] for row in exact_event_times] == [
        9007199254740993, 9007199254740994,
    ], "distinct exact times collapsed")

    long_decimal_times = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t1234567890123456789012345678.90123456789\t1\tA\n"
        "A2\t1234567890123456789012345678.90123456790\t0\tA\n"
        "B1\t1234567890123456789012345678.90123456789\t0\tB\n"
        "B2\t1234567890123456789012345678.90123456791\t1\tB\n"
    )
    long_event_times = analyze(
        long_decimal_times.encode(), long_decimal_times
    )["event_times"]
    check(
        [row["time"] for row in long_event_times]
        == [
            "1234567890123456789012345678.90123456789",
            "1234567890123456789012345678.90123456791",
        ],
        "long exact decimal event times were rounded",
    )

    zero_variance = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t1\t1\tA\nB1\t0\t0\tB\n"
    )
    zero_result = analyze(zero_variance.encode(), zero_variance)
    check(zero_result["comparison"] == {
        "status": "not-estimable",
        "reason": "zero-total-variance",
        "chi_square": None,
        "degrees_of_freedom": 1,
        "p_value": None,
        "p_value_status": "not-estimable",
    }, "zero-variance result differs")

    separated_records: list[dict[str, Any]] = []
    for index in range(1000):
        separated_records.append({
            "subject_id": f"A{index}",
            "time": Decimal(index + 1),
            "event": 1,
            "group": "A",
        })
        separated_records.append({
            "subject_id": f"B{index}",
            "time": Decimal(2000),
            "event": 0,
            "group": "B",
        })
    underflow = log_rank(separated_records, ["A", "B"])["comparison"]
    check(
        underflow["status"] == "estimated"
        and underflow["p_value"] is None
        and underflow["p_value_status"] == "underflow",
        "finite extreme tail was emitted as an exact zero p-value",
    )

    no_events = (
        "subject_id\ttime\tevent\tgroup\n"
        "A1\t1\t0\tA\nB1\t2\t0\tB\n"
    )
    no_event_result = analyze(no_events.encode(), no_events)
    check(no_event_result["event_times"] == [] and
          no_event_result["comparison"]["status"] == "not-estimable",
          "all-censored result differs")

    expect_issue("invalid-header", lambda: parse_subjects(
        "subject_id\ttime\tevent\nS1\t1\t1\n"))
    expect_issue("duplicate-subject-id", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\t1\tA\nS1\t2\t0\tB\n"))
    expect_issue("negative-time", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t-1\t1\tA\nS2\t1\t0\tB\n"))
    expect_issue("invalid-time", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\tNaN\t1\tA\nS2\t1\t0\tB\n"))
    expect_issue("time-out-of-range", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1e999999\t1\tA\nS2\t1\t0\tB\n"))
    expect_issue("invalid-event", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\ttrue\tA\nS2\t1\t0\tB\n"))
    expect_issue("empty-value", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\t1\t\n"))
    expect_issue("group-count-not-two", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\t1\tA\n"))
    expect_issue("group-count-not-two", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\n"
        "S1\t1\t1\tA\nS2\t1\t0\tB\nS3\t2\t0\tC\n"))
    expect_issue("ragged-row", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\nS1\t1\t1\n"))
    expect_issue("no-subjects", lambda: parse_subjects(
        "subject_id\ttime\tevent\tgroup\n"))

    with tempfile.TemporaryDirectory(prefix="log-rank-selftest-") as temporary_name:
        root = Path(temporary_name)
        regular = root / "subjects.tsv"
        regular.write_text(fixture, encoding="utf-8")
        payload, text = read_local_file(regular, root=root)
        check(payload == fixture.encode() and text == fixture,
              "regular input read differs")
        linked = root / "linked.tsv"
        linked.symlink_to(regular)
        expect_issue("input-not-regular-file", lambda: read_local_file(
            linked, root=root))
        expect_issue("parent-traversal", lambda: read_local_file(
            Path("..") / "outside.tsv", root=root))

        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "subjects.tsv").write_text(fixture, encoding="utf-8")
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
            "event_times": len(report["event_times"]),
            "status": "completed",
            "subjects": report["input"]["subject_count"],
            "test_status": report["comparison"]["status"],
        }, sort_keys=True))
        return 0
    except InputError as exc:
        print(json.dumps({
            "analysis_performed": False,
            "issues": exc.issues,
            "status": "invalid-input",
        }, sort_keys=True), file=sys.stderr)
        return 2
    except (FileExistsError, FileNotFoundError, IsADirectoryError,
            NotADirectoryError, PermissionError) as exc:
        print(json.dumps({
            "analysis_performed": False,
            "error": str(exc),
            "status": "invalid-output",
        }, sort_keys=True), file=sys.stderr)
        return 3
    except OSError as exc:
        print(json.dumps({
            "analysis_performed": False,
            "error": str(exc),
            "status": "io-error",
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
