#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded missing-outcome profile and aggregate sensitivity report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import stat
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "0.9.0"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100_000
MAX_GROUPS = 1_000
MAX_GROUP_LABEL_CHARS = 256
MAX_DELTAS = 101
MAX_SCENARIOS = 100_000
MAX_REPORTED_ISSUES = 100


class InputError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("input validation failed")
        self.issues = issues


def _issue(code: str, *, line: int | None = None, field: str | None = None,
           value: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code}
    if line is not None:
        item["line"] = line
    if field is not None:
        item["field"] = field
    if value is not None:
        item["value"] = value
    return item


def read_input(path: Path) -> tuple[bytes, str]:
    """Read one stable, regular, non-symlink UTF-8 input within the byte cap."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise InputError([_issue("input-not-regular-file")])
        if before.st_size > MAX_INPUT_BYTES:
            raise InputError([_issue("input-too-large")])

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise InputError([_issue("input-not-regular-file")])
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise InputError([_issue("input-changed-during-read")])
            if opened.st_size > MAX_INPUT_BYTES:
                raise InputError([_issue("input-too-large")])
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read(MAX_INPUT_BYTES + 1)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)

        after_path = path.lstat()
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise InputError([_issue("input-too-large")])
        if any(getattr(opened, field) != getattr(after_open, field) for field in stable_fields):
            raise InputError([_issue("input-changed-during-read")])
        if any(getattr(after_open, field) != getattr(after_path, field) for field in stable_fields):
            raise InputError([_issue("input-changed-during-read")])
        try:
            return payload, payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError([_issue("input-not-utf8")]) from exc
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise InputError([_issue("input-unreadable")]) from exc


def choose_delimiter(path: Path, requested: str, text: str) -> tuple[str, str]:
    if requested == "csv":
        return ",", "csv"
    if requested == "tsv":
        return "\t", "tsv"
    if path.suffix.lower() == ".csv":
        return ",", "csv"
    if path.suffix.lower() == ".tsv":
        return "\t", "tsv"
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters="\t,").delimiter
    except csv.Error as exc:
        raise InputError([_issue("delimiter-not-detected")]) from exc
    return delimiter, "tsv" if delimiter == "\t" else "csv"


def parse_delta_grid(raw: str) -> list[float]:
    tokens = [token.strip() for token in raw.split(",")]
    if not tokens or any(not token for token in tokens):
        raise InputError([_issue("invalid-delta-grid", field="delta-grid")])
    if len(tokens) > MAX_DELTAS:
        raise InputError([_issue("too-many-deltas", field="delta-grid", value=len(tokens))])
    deltas: list[float] = []
    seen: set[float] = set()
    for token in tokens:
        try:
            value = float(token)
        except ValueError:
            value = math.nan
        if not math.isfinite(value):
            raise InputError([_issue("non-finite-delta", field="delta-grid", value=token)])
        value = 0.0 if value == 0.0 else value
        if value in seen:
            raise InputError([_issue("duplicate-delta", field="delta-grid", value=token)])
        seen.add(value)
        deltas.append(value)
    return deltas


def parse_table(
    text: str,
    *,
    delimiter: str,
    outcome_column: str,
    group_column: str | None,
    missing_tokens: set[str],
    lower_bound: float,
    upper_bound: float,
    max_rows: int = MAX_ROWS,
) -> tuple[list[float | None], dict[str, list[float | None]]]:
    if group_column == outcome_column:
        raise InputError([_issue("column-role-collision", field=outcome_column)])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
    if reader.fieldnames is None:
        raise InputError([_issue("missing-header")])
    fields = [field.strip() for field in reader.fieldnames]
    reader.fieldnames = fields
    if not fields or any(not field for field in fields) or len(fields) != len(set(fields)):
        raise InputError([_issue("invalid-or-duplicate-header")])
    required = [outcome_column] + ([group_column] if group_column else [])
    missing_fields = [field for field in required if field not in fields]
    if missing_fields:
        raise InputError([_issue("missing-column", field=field) for field in missing_fields])

    overall: list[float | None] = []
    groups: dict[str, list[float | None]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    issue_count = 0

    def record(item: dict[str, Any]) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < MAX_REPORTED_ISSUES:
            issues.append(item)

    try:
        for row_number, raw in enumerate(reader, start=1):
            line = row_number + 1
            if row_number > max_rows:
                record(_issue("too-many-rows", line=line))
                break
            if raw.get(None) is not None:
                record(_issue("ragged-row", line=line))
                continue
            row = {field: "" if raw.get(field) is None else str(raw[field]).strip()
                   for field in fields}
            group = ""
            group_valid = False
            if group_column:
                group = row[group_column]
                if not group:
                    record(_issue("missing-group", line=line, field=group_column))
                elif len(group) > MAX_GROUP_LABEL_CHARS:
                    record(_issue("group-label-too-long", line=line, field=group_column))
                elif group not in groups and len(groups) >= MAX_GROUPS:
                    record(_issue("too-many-groups", line=line, field=group_column))
                else:
                    group_valid = True

            raw_outcome = row[outcome_column]
            value: float | None
            if raw_outcome in missing_tokens:
                value = None
            else:
                try:
                    value = float(raw_outcome)
                except ValueError:
                    value = math.nan
                if not math.isfinite(value):
                    record(_issue("non-finite-or-nonnumeric-outcome", line=line,
                                  field=outcome_column, value=raw_outcome))
                elif not lower_bound <= value <= upper_bound:
                    record(_issue("outcome-outside-declared-bounds", line=line,
                                  field=outcome_column, value=raw_outcome))

            overall.append(value)
            if group_column and group_valid:
                groups[group].append(value)
    except csv.Error:
        record(_issue("malformed-delimited-input"))

    if not overall:
        record(_issue("no-data-rows"))
    if issue_count:
        if issue_count > len(issues):
            issues.append(_issue("additional-issues-omitted",
                                 value=issue_count - len(issues)))
        raise InputError(issues)
    return overall, dict(groups)


def _mean(values: list[float]) -> float:
    result = math.fsum(value / len(values) for value in values)
    return 0.0 if result == 0.0 else result


def _weighted_mean(observed_mean: float, observed_count: int,
                   missing_mean: float, missing_count: int) -> float:
    total = observed_count + missing_count
    result = math.fsum((observed_mean * (observed_count / total),
                        missing_mean * (missing_count / total)))
    return 0.0 if result == 0.0 else result


def profile(values: list[float | None], *, lower_bound: float,
            upper_bound: float, deltas: list[float]) -> dict[str, Any]:
    observed = [value for value in values if value is not None]
    observed_count = len(observed)
    missing_count = len(values) - observed_count
    complete_mean = _mean(observed) if observed else None

    if complete_mean is None:
        lower_mean = lower_bound
        upper_mean = upper_bound
    else:
        lower_mean = _weighted_mean(complete_mean, observed_count, lower_bound, missing_count)
        upper_mean = _weighted_mean(complete_mean, observed_count, upper_bound, missing_count)

    scenarios: list[dict[str, Any]] = []
    for delta in deltas:
        if missing_count == 0:
            scenarios.append({
                "delta": delta,
                "status": "not-applicable-no-missing-values",
                "assumed_missing_outcome_mean": None,
                "combined_mean": complete_mean,
            })
            continue
        if complete_mean is None:
            scenarios.append({
                "delta": delta,
                "status": "not-estimable-no-observed-values",
                "assumed_missing_outcome_mean": None,
                "combined_mean": None,
            })
            continue
        assumed_mean = complete_mean + delta
        if not math.isfinite(assumed_mean) or not lower_bound <= assumed_mean <= upper_bound:
            scenarios.append({
                "delta": delta,
                "status": "outside-declared-bounds",
                "assumed_missing_outcome_mean": assumed_mean if math.isfinite(assumed_mean) else None,
                "combined_mean": None,
            })
            continue
        scenarios.append({
            "delta": delta,
            "status": "within-declared-bounds",
            "assumed_missing_outcome_mean": 0.0 if assumed_mean == 0.0 else assumed_mean,
            "combined_mean": _weighted_mean(
                complete_mean, observed_count, assumed_mean, missing_count
            ),
        })

    return {
        "total_rows": len(values),
        "observed_rows": observed_count,
        "missing_rows": missing_count,
        "missing_fraction": missing_count / len(values),
        "complete_case_mean": complete_mean,
        "mean_if_missing_at_lower_bound": lower_mean,
        "mean_if_missing_at_upper_bound": upper_mean,
        "delta_sensitivity": scenarios,
    }


def analyze(
    payload: bytes,
    text: str,
    *,
    delimiter: str,
    delimiter_name: str,
    outcome_column: str,
    group_column: str | None,
    declared_missing_tokens: list[str],
    lower_bound: float,
    upper_bound: float,
    deltas: list[float],
) -> dict[str, Any]:
    if not math.isfinite(lower_bound) or not math.isfinite(upper_bound):
        raise InputError([_issue("non-finite-bound", field="bounds")])
    if lower_bound >= upper_bound:
        raise InputError([_issue("invalid-bound-order", field="bounds")])
    normalized_tokens = [token.strip() for token in declared_missing_tokens]
    if any(not token for token in normalized_tokens):
        raise InputError([_issue("empty-explicit-missing-token", field="missing-token")])
    if len(normalized_tokens) != len(set(normalized_tokens)):
        raise InputError([_issue("duplicate-missing-token", field="missing-token")])
    missing_tokens = {"", *normalized_tokens}
    overall, groups = parse_table(
        text,
        delimiter=delimiter,
        outcome_column=outcome_column,
        group_column=group_column,
        missing_tokens=missing_tokens,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )
    profile_count = 1 + (len(groups) if group_column else 0)
    if profile_count * len(deltas) > MAX_SCENARIOS:
        raise InputError([_issue("too-many-group-delta-scenarios",
                                 value=profile_count * len(deltas))])

    grouped_profiles = [
        {"group": group, **profile(groups[group], lower_bound=lower_bound,
                                    upper_bound=upper_bound, deltas=deltas)}
        for group in sorted(groups)
    ]
    return {
        "schema_version": "1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": {"name": "analyze_missing_outcomes", "version": VERSION},
        "input": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "delimiter": delimiter_name,
            "outcome_column": outcome_column,
            "group_column": group_column,
            "missing_tokens": ["", *sorted(normalized_tokens)],
        },
        "declared_assumptions": {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "delta_grid": deltas,
            "delta_definition": "assumed_missing_outcome_mean = complete_case_mean + delta",
            "missingness_mechanism": "not-inferred",
        },
        "overall": profile(overall, lower_bound=lower_bound,
                           upper_bound=upper_bound, deltas=deltas),
        "groups": grouped_profiles,
        "limitations": [
            "Descriptive aggregate scenarios only; no MCAR, MAR, or MNAR inference.",
            "No row-level imputation, model fitting, hypothesis testing, or bias correction.",
            "Bounds, missing tokens, grouping, and delta values are user-declared assumptions.",
        ],
    }


def _safe_output_target(path: Path, root: Path | None = None) -> Path:
    lexical_root = Path.cwd() if root is None else root
    if lexical_root.is_symlink():
        raise PermissionError(f"output root is a symlink: {lexical_root}")
    resolved_root = lexical_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"output root is not a directory: {resolved_root}")
    if ".." in path.parts:
        raise PermissionError(f"output path contains parent traversal: {path}")
    if path.is_absolute():
        try:
            candidate = resolved_root / path.relative_to(lexical_root)
        except ValueError:
            candidate = path
    else:
        candidate = resolved_root / path
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PermissionError(f"output is outside the allowed root: {candidate}") from exc
    if not relative.parts:
        raise IsADirectoryError(f"output is not a file path: {candidate}")
    cursor = resolved_root
    for part in relative.parts[:-1]:
        cursor /= part
        if cursor.is_symlink():
            raise PermissionError(f"output parent contains a symlink: {cursor}")
        if not cursor.is_dir():
            raise FileNotFoundError(f"output parent does not exist: {cursor}")
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError(candidate)
    return candidate


def _unlink_owned(path: Path, identity: tuple[int, int]) -> bool:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    path.unlink()
    return True


def _is_owned(path: Path, identity: tuple[int, int]) -> bool:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rollback_owned(directory: Path, identity: tuple[int, int], paths: tuple[Path, ...]) -> None:
    failures: list[str] = []
    for path in paths:
        try:
            if not _unlink_owned(path, identity):
                failures.append(f"{path.name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{path.name}:{exc.__class__.__name__}")
    try:
        _fsync_directory(directory)
    except OSError as exc:
        failures.append(f"directory:{exc.__class__.__name__}")
    if failures:
        raise OSError("publication rollback failed: " + ", ".join(failures))


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def write_new(path: Path, text: str, *, root: Path | None = None) -> Path:
    target = _safe_output_target(path, root)
    payload = text.encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-",
                                                   dir=target.parent)
    temporary = Path(temporary_name)
    temporary_stat = os.fstat(descriptor)
    identity = (temporary_stat.st_dev, temporary_stat.st_ino)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        try:
            os.close(descriptor)
        finally:
            descriptor = -1
        os.link(temporary, target)
        published = True
        if not _is_owned(target, identity):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned(temporary, identity):
            raise OSError("temporary output identity changed before cleanup")
        _fsync_directory(target.parent)
        if not _is_owned(target, identity):
            raise OSError("published output identity changed before completion")
    except BaseException as original:
        if descriptor >= 0:
            os.close(descriptor)
        paths = (target, temporary) if published else (temporary,)
        try:
            _rollback_owned(target.parent, identity, paths)
        except OSError as rollback_error:
            raise rollback_error from original
        raise
    return target


def self_test() -> None:
    text = "arm,outcome\nA,10\nA,\nA,NA\nB,20\nB,40\nC,NA\n"
    payload = text.encode()
    deltas = parse_delta_grid("-20,0,10")
    report = analyze(
        payload,
        text,
        delimiter=",",
        delimiter_name="csv",
        outcome_column="outcome",
        group_column="arm",
        declared_missing_tokens=["NA"],
        lower_bound=0.0,
        upper_bound=100.0,
        deltas=deltas,
    )
    if report["overall"]["total_rows"] != 6 or report["overall"]["missing_rows"] != 3:
        raise RuntimeError("overall missingness self-test differs")
    groups = {item["group"]: item for item in report["groups"]}
    if groups["A"]["complete_case_mean"] != 10.0:
        raise RuntimeError("complete-case mean self-test differs")
    if not math.isclose(groups["A"]["mean_if_missing_at_upper_bound"], 70.0):
        raise RuntimeError("upper-bound sensitivity self-test differs")
    if groups["A"]["delta_sensitivity"][0]["status"] != "outside-declared-bounds":
        raise RuntimeError("out-of-bounds delta self-test differs")
    if not math.isclose(groups["A"]["delta_sensitivity"][2]["combined_mean"], 50.0 / 3.0):
        raise RuntimeError("delta sensitivity value self-test differs")
    if groups["B"]["delta_sensitivity"][1]["status"] != "not-applicable-no-missing-values":
        raise RuntimeError("complete group delta self-test differs")
    if groups["C"]["delta_sensitivity"][1]["status"] != "not-estimable-no-observed-values":
        raise RuntimeError("all-missing group self-test differs")
    second = analyze(
        payload,
        text,
        delimiter=",",
        delimiter_name="csv",
        outcome_column="outcome",
        group_column="arm",
        declared_missing_tokens=["NA"],
        lower_bound=0.0,
        upper_bound=100.0,
        deltas=deltas,
    )
    if json.dumps(report, sort_keys=True) != json.dumps(second, sort_keys=True):
        raise RuntimeError("deterministic report self-test differs")

    bad = "outcome\nNaN\n101\nword\n"
    try:
        analyze(bad.encode(), bad, delimiter=",", delimiter_name="csv",
                outcome_column="outcome", group_column=None,
                declared_missing_tokens=[], lower_bound=0.0, upper_bound=100.0,
                deltas=[0.0])
    except InputError as exc:
        if [item["code"] for item in exc.issues] != [
            "non-finite-or-nonnumeric-outcome",
            "outcome-outside-declared-bounds",
            "non-finite-or-nonnumeric-outcome",
        ]:
            raise RuntimeError("invalid outcome self-test differs")
    else:
        raise AssertionError("invalid outcomes were accepted")

    try:
        parse_delta_grid("0,-0")
    except InputError as exc:
        if [item["code"] for item in exc.issues] != ["duplicate-delta"]:
            raise RuntimeError("duplicate delta self-test differs")
    else:
        raise AssertionError("duplicate deltas were accepted")

    try:
        parse_table("outcome\n1\n2\n3\n", delimiter=",", outcome_column="outcome",
                    group_column=None, missing_tokens={""}, lower_bound=0.0,
                    upper_bound=10.0, max_rows=2)
    except InputError as exc:
        if [item["code"] for item in exc.issues] != ["too-many-rows"]:
            raise RuntimeError("row-cap self-test differs")
    else:
        raise AssertionError("row cap was not enforced")

    with tempfile.TemporaryDirectory(prefix="missing-outcomes-selftest-") as temporary_name:
        test_root = Path(temporary_name)
        regular = test_root / "input.csv"
        regular.write_bytes(payload)
        read_payload, read_text = read_input(regular)
        if read_payload != payload or read_text != text:
            raise RuntimeError("regular input self-test differs")
        linked = test_root / "linked.csv"
        linked.symlink_to(regular)
        try:
            read_input(linked)
        except InputError as exc:
            if [item["code"] for item in exc.issues] != ["input-not-regular-file"]:
                raise RuntimeError("symlink input self-test differs")
        else:
            raise AssertionError("symlink input was accepted")
        oversized = test_root / "oversized.csv"
        with oversized.open("wb") as handle:
            handle.truncate(MAX_INPUT_BYTES + 1)
        try:
            read_input(oversized)
        except InputError as exc:
            if [item["code"] for item in exc.issues] != ["input-too-large"]:
                raise RuntimeError("oversized input self-test differs")
        else:
            raise AssertionError("oversized input was accepted")
        output = test_root / "report.json"
        write_new(output, "{}\n", root=test_root)
        try:
            write_new(output, "replacement\n", root=test_root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output was replaced")
        if output.read_text(encoding="utf-8") != "{}\n":
            raise RuntimeError("no-overwrite self-test differs")
        try:
            write_new(Path("..") / "escape.json", "{}\n", root=test_root)
        except PermissionError:
            pass
        else:
            raise AssertionError("parent traversal output was accepted")

        zero_output = test_root / "zero-write.json"
        real_write = os.write
        os.write = lambda _descriptor, _payload: 0
        try:
            try:
                write_new(zero_output, "{}\n", root=test_root)
            except OSError:
                pass
            else:
                raise AssertionError("zero-byte output write did not fail")
        finally:
            os.write = real_write
        if zero_output.exists() or list(test_root.glob(f".{zero_output.name}.tmp-*")):
            raise RuntimeError("zero-byte output write left publication artifacts")

        final_race = test_root / "final-race.json"
        real_unlink = os.unlink
        final_replaced = False

        def replace_final_during_cleanup(path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                                         *args: Any, **kwargs: Any) -> None:
            nonlocal final_replaced
            if not final_replaced and Path(path).name.startswith(f".{final_race.name}.tmp-"):
                final_replaced = True
                real_unlink(final_race)
                competitor = os.open(final_race, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    _write_all(competitor, b"competitor\n")
                    os.fsync(competitor)
                finally:
                    os.close(competitor)
            real_unlink(path, *args, **kwargs)

        os.unlink = replace_final_during_cleanup
        try:
            try:
                write_new(final_race, "{}\n", root=test_root)
            except OSError:
                pass
            else:
                raise AssertionError("final-inode replacement was reported as success")
        finally:
            os.unlink = real_unlink
        if final_race.read_bytes() != b"competitor\n":
            raise RuntimeError("rollback removed a competing final output")
        if list(test_root.glob(f".{final_race.name}.tmp-*")):
            raise RuntimeError("final-inode race left an owned temporary output")

    print(json.dumps({"checks": 12, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--outcome-column", default="outcome")
    result.add_argument("--group-column")
    result.add_argument("--lower-bound", type=float)
    result.add_argument("--upper-bound", type=float)
    result.add_argument("--delta-grid")
    result.add_argument("--missing-token", action="append", default=[])
    result.add_argument("--delimiter", choices=("auto", "csv", "tsv"), default="auto")
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    missing = [name for name in ("input", "output", "lower_bound", "upper_bound", "delta_grid")
               if getattr(args, name) is None]
    if missing:
        parser().error("required for execution: " + ", ".join(
            f"--{name.replace('_', '-')}" for name in missing
        ))
    try:
        deltas = parse_delta_grid(args.delta_grid)
        payload, text = read_input(args.input)
        delimiter, delimiter_name = choose_delimiter(args.input, args.delimiter, text)
        report = analyze(
            payload,
            text,
            delimiter=delimiter,
            delimiter_name=delimiter_name,
            outcome_column=args.outcome_column,
            group_column=args.group_column,
            declared_missing_tokens=args.missing_token,
            lower_bound=args.lower_bound,
            upper_bound=args.upper_bound,
            deltas=deltas,
        )
        rendered = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
        write_new(args.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "groups": len(report["groups"]),
            "output": str(args.output),
            "rows": report["overall"]["total_rows"],
            "status": "completed",
        }, sort_keys=True))
        return 0
    except InputError as exc:
        print(json.dumps({
            "analysis_performed": False,
            "issues": exc.issues,
            "status": "invalid-input",
        }, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({
            "analysis_performed": False,
            "error": str(exc),
            "status": "io-error",
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
