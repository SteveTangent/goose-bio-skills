#!/usr/bin/env python3
"""Validate a delimited p-value table and apply BH or Holm by family."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "0.2.0"


class InputError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("input validation failed")
        self.issues = issues


def _issue(code: str, *, line: int | None = None, record_id: str | None = None,
           field: str | None = None, value: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code}
    if line is not None:
        item["line"] = line
    if record_id is not None:
        item["record_id"] = record_id
    if field is not None:
        item["field"] = field
    if value is not None:
        item["value"] = value
    return item


def _delimiter(path: Path, requested: str, text: str) -> str:
    if requested == "tsv":
        return "\t"
    if requested == "csv":
        return ","
    if path.suffix.lower() == ".tsv":
        return "\t"
    if path.suffix.lower() == ".csv":
        return ","
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters="\t,").delimiter
    except csv.Error as exc:
        raise InputError([_issue("delimiter-not-detected")]) from exc


def parse_table(
    text: str,
    *,
    delimiter: str,
    id_column: str,
    p_column: str,
    family_column: str | None,
) -> tuple[list[str], list[dict[str, str]], list[float], dict[str, list[int]]]:
    role_columns = [id_column, p_column] + ([family_column] if family_column else [])
    if len(role_columns) != len(set(role_columns)):
        raise InputError([_issue("column-role-collision", field=field)
                          for field in sorted({field for field in role_columns
                                               if role_columns.count(field) > 1})])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
    if reader.fieldnames is None:
        raise InputError([_issue("missing-header")])
    fields = [field.strip() for field in reader.fieldnames]
    reader.fieldnames = fields
    if not fields or any(not field for field in fields) or len(fields) != len(set(fields)):
        raise InputError([_issue("invalid-or-duplicate-header")])
    if family_column is None and "family_id" in fields:
        raise InputError([_issue("unselected-family-column", field="family_id")])
    required = role_columns
    missing = [field for field in required if field not in fields]
    if missing:
        raise InputError([_issue("missing-column", field=field) for field in missing])
    reserved = [field for field in ("p_adjusted", "decision") if field in fields]
    if reserved:
        raise InputError([_issue("output-column-already-present", field=field) for field in reserved])
    canonical_roles = ((id_column, "record_id"), (p_column, "p_value"))
    if family_column:
        canonical_roles += ((family_column, "family_id"),)
    collisions = [canonical for source, canonical in canonical_roles
                  if source != canonical and canonical in fields]
    if collisions:
        raise InputError([_issue("canonical-output-column-collision", field=field)
                          for field in collisions])

    rows: list[dict[str, str]] = []
    p_values: list[float] = []
    families: dict[str, list[int]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        for line, raw in enumerate(reader, start=2):
            values = [value for key, value in raw.items() if key is not None]
            if raw.get(None) is not None:
                issues.append(_issue("ragged-row", line=line))
                continue
            if all(value is None or not str(value).strip() for value in values):
                continue
            row = {field: "" if raw.get(field) is None else str(raw[field]).strip() for field in fields}
            record_id = row[id_column]
            if not record_id:
                issues.append(_issue("missing-record-id", line=line, field=id_column))
            elif record_id in seen_ids:
                issues.append(_issue("duplicate-record-id", line=line, record_id=record_id, field=id_column))
            else:
                seen_ids.add(record_id)

            raw_p = row[p_column]
            try:
                p_value = float(raw_p)
            except ValueError:
                p_value = math.nan
            if not raw_p:
                issues.append(_issue("missing-p-value", line=line, record_id=record_id or None, field=p_column))
            elif not math.isfinite(p_value):
                issues.append(_issue("non-finite-p-value", line=line, record_id=record_id or None,
                                     field=p_column, value=raw_p))
            elif not 0.0 <= p_value <= 1.0:
                issues.append(_issue("p-value-out-of-range", line=line, record_id=record_id or None,
                                     field=p_column, value=raw_p))

            family = "__all__"
            if family_column:
                family = row[family_column]
                if not family:
                    issues.append(_issue("missing-family", line=line, record_id=record_id or None,
                                         field=family_column))

            index = len(rows)
            rows.append(row)
            p_values.append(p_value)
            families[family].append(index)
    except csv.Error:
        issues.append(_issue("malformed-delimited-input"))

    if not rows:
        issues.append(_issue("no-data-rows"))
    if issues:
        raise InputError(issues)
    return fields, rows, p_values, dict(families)


def adjust(values: list[float], method: str) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    adjusted = [0.0] * len(values)
    count = len(values)
    if method == "bh":
        running = 1.0
        for rank_index in range(count - 1, -1, -1):
            index = order[rank_index]
            rank = rank_index + 1
            running = min(running, values[index] * count / rank)
            adjusted[index] = min(1.0, running)
    elif method == "holm":
        running = 0.0
        for rank_index, index in enumerate(order):
            running = max(running, values[index] * (count - rank_index))
            adjusted[index] = min(1.0, running)
    else:
        raise ValueError(f"unsupported method: {method}")
    return adjusted


def process(
    text: str,
    *,
    delimiter: str,
    id_column: str,
    p_column: str,
    family_column: str | None,
    method: str,
    alpha: float,
) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise InputError([_issue("invalid-alpha", field="alpha", value=str(alpha))])
    fields, rows, p_values, families = parse_table(
        text,
        delimiter=delimiter,
        id_column=id_column,
        p_column=p_column,
        family_column=family_column,
    )
    all_adjusted = [0.0] * len(rows)
    for indices in families.values():
        family_adjusted = adjust([p_values[index] for index in indices], method)
        for index, value in zip(indices, family_adjusted, strict=True):
            all_adjusted[index] = value

    role_sources = {id_column, p_column} | ({family_column} if family_column else set())
    other_fields = [field for field in fields if field not in role_sources]
    output_fields = ["record_id", "p_value", "p_adjusted", "decision"]
    if family_column:
        output_fields.append("family_id")
    output_fields.extend(other_fields)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=output_fields,
                            delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    for row, value in zip(rows, all_adjusted, strict=True):
        rendered_row = {
            "record_id": row[id_column],
            "p_value": row[p_column],
            "p_adjusted": repr(value),
            "decision": "rejected" if value <= alpha else "not-rejected",
        }
        if family_column:
            rendered_row["family_id"] = row[family_column]
        rendered_row.update({field: row[field] for field in other_fields})
        writer.writerow(rendered_row)
    summary = {
        "status": "success",
        "analysis_performed": True,
        "method": method,
        "alpha": alpha,
        "records": len(rows),
        "families": len(families),
    }
    return output.getvalue(), summary


def _safe_output_target(path: Path, root: Path | None) -> Path:
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


def write_new(path: Path, text: str, *, root: Path | None = None) -> Path:
    target = _safe_output_target(path, root)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    temporary = Path(temporary_name)
    published = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
        published = True
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        if published:
            target.unlink(missing_ok=True)
        raise
    temporary.unlink()
    directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return target


def self_test() -> None:
    holm_text = "record_id\tp_value\nA\t0.010\nB\t0.016\nC\t0.025\nD\t0.200\n"
    rendered, summary = process(holm_text, delimiter="\t", id_column="record_id",
                                p_column="p_value", family_column=None,
                                method="holm", alpha=0.05)
    result = list(csv.DictReader(io.StringIO(rendered), delimiter="\t"))
    if [float(row["p_adjusted"]) for row in result] != [0.04, 0.048, 0.05, 0.2]:
        raise RuntimeError("Holm self-test values differ")
    if [row["decision"] for row in result] != ["rejected", "rejected", "rejected", "not-rejected"]:
        raise RuntimeError("Holm self-test decisions differ")
    if summary["records"] != 4 or summary["families"] != 1:
        raise RuntimeError("Holm self-test summary differs")

    grouped = "record_id,family_id,p_value\nA,F1,0.01\nB,F1,0.04\nC,F2,0.01\nD,F2,0.04\n\n"
    rendered, _ = process(grouped, delimiter=",", id_column="record_id", p_column="p_value",
                          family_column="family_id", method="bh", alpha=0.05)
    result = list(csv.DictReader(io.StringIO(rendered)))
    if [float(row["p_adjusted"]) for row in result] != [0.02, 0.04, 0.02, 0.04]:
        raise RuntimeError("grouped BH self-test values differ")

    bad = "record_id\tp_value\nOK0\t0\nNEG\t-0.01\nHIGH\t1.2\nNAN\tNaN\nINF\tInf\nMISS\t\nOK1\t1\n"
    try:
        process(bad, delimiter="\t", id_column="record_id", p_column="p_value",
                family_column=None, method="bh", alpha=0.05)
    except InputError as exc:
        if [item["code"] for item in exc.issues] != [
            "p-value-out-of-range", "p-value-out-of-range", "non-finite-p-value",
            "non-finite-p-value", "missing-p-value"
        ]:
            raise RuntimeError("invalid p-value self-test result differs")
    else:
        raise AssertionError("invalid p-values were accepted")
    boundary = math.nextafter(0.05, math.inf)
    rendered, _ = process(f"record_id\tp_value\nA\t{boundary!r}\n", delimiter="\t",
                          id_column="record_id", p_column="p_value", family_column=None,
                          method="holm", alpha=0.05)
    boundary_row = next(csv.DictReader(io.StringIO(rendered), delimiter="\t"))
    if float(boundary_row["p_adjusted"]) <= 0.05 or boundary_row["decision"] != "not-rejected":
        raise RuntimeError("serialized alpha boundary contradicts its decision")

    print(json.dumps({"status": "pass", "version": VERSION, "checks": 4}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--validation-output", type=Path)
    result.add_argument("--method", choices=("bh", "holm"))
    result.add_argument("--alpha", type=float)
    result.add_argument("--id-column", default="record_id")
    result.add_argument("--p-column", default="p_value")
    result.add_argument("--family-column")
    result.add_argument("--delimiter", choices=("auto", "csv", "tsv"), default="auto")
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    missing = [name for name in ("input", "output", "validation_output", "method", "alpha")
               if getattr(args, name) is None]
    if missing:
        parser().error("required for execution: " + ", ".join(f"--{name}" for name in missing))
    if os.path.abspath(args.output) == os.path.abspath(args.validation_output):
        parser().error("--output and --validation-output must be different paths")
    try:
        text = args.input.read_text(encoding="utf-8-sig")
        delimiter = _delimiter(args.input, args.delimiter, text)
        rendered, summary = process(
            text,
            delimiter=delimiter,
            id_column=args.id_column,
            p_column=args.p_column,
            family_column=args.family_column,
            method=args.method,
            alpha=args.alpha,
        )
        write_new(args.output, rendered)
        summary["output"] = str(args.output)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except InputError as exc:
        report = {"status": "invalid-input", "analysis_performed": False,
                  "reason_code": "invalid-input", "issues": exc.issues}
        try:
            write_new(args.validation_output, json.dumps(report, sort_keys=True) + "\n")
        except (OSError, UnicodeError) as write_exc:
            print(json.dumps({"status": "error", "analysis_performed": False,
                              "reason_code": "validation-output-error", "error": str(write_exc)},
                             sort_keys=True), file=sys.stderr)
            return 3
        print(json.dumps(report, sort_keys=True))
        return 2
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"status": "error", "analysis_performed": False,
                          "reason_code": "io-error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
