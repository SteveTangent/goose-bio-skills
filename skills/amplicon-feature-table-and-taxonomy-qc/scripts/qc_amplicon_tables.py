#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded descriptive QC report for local amplicon TSV tables."""

from __future__ import annotations

import argparse
import csv
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
MAX_FEATURES = 50_000
MAX_SAMPLES = 2_000
MAX_METADATA_ROWS = 10_000
MAX_CELLS = 2_000_000
MAX_ID_CHARS = 256
MAX_TAXONOMY_VALUE_CHARS = 512
MAX_COUNT = 2**63 - 1
MAX_NEGATIVE_CONTROL_VALUES = 32
CANONICAL_RANKS = ("domain", "phylum", "class", "order", "family", "genus", "species")
ASCII_INTEGER = re.compile(r"[0-9]+\Z")


class InputError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("input validation failed")
        self.issues = issues


def issue(code: str, *, role: str | None = None, line: int | None = None,
          field: str | None = None, value: Any = None) -> dict[str, Any]:
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


def read_local_file(path: Path, role: str) -> tuple[bytes, str]:
    """Read one stable regular non-symlink UTF-8 file within the byte cap."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise InputError([issue("input-not-regular-file", role=role)])
        if before.st_size > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large", role=role)])

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise InputError([issue("input-not-regular-file", role=role)])
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise InputError([issue("input-changed-during-read", role=role)])
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read(MAX_INPUT_BYTES + 1)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)

        after_path = path.lstat()
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large", role=role)])
        if any(getattr(opened, key) != getattr(after_open, key) for key in stable):
            raise InputError([issue("input-changed-during-read", role=role)])
        if any(getattr(after_open, key) != getattr(after_path, key) for key in stable):
            raise InputError([issue("input-changed-during-read", role=role)])
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError([issue("input-not-utf8", role=role)]) from exc
        if "\x00" in text:
            raise InputError([issue("nul-byte-in-input", role=role)])
        return payload, text
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise InputError([issue("input-unreadable", role=role)]) from exc


def parse_tsv(text: str, role: str, max_rows: int) -> tuple[list[str], list[list[str]]]:
    try:
        reader = csv.reader(io.StringIO(text), delimiter="\t", strict=True)
        header = next(reader)
    except StopIteration as exc:
        raise InputError([issue("missing-header", role=role)]) from exc
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv", role=role)]) from exc

    if not header or any(not cell for cell in header):
        raise InputError([issue("empty-header", role=role)])
    if len(header) != len(set(header)):
        raise InputError([issue("duplicate-header", role=role)])
    for field in header:
        validate_token(field, role=role, field="header", max_chars=MAX_ID_CHARS)

    rows: list[list[str]] = []
    try:
        for row_number, row in enumerate(reader, start=1):
            line = row_number + 1
            if row_number > max_rows:
                raise InputError([issue("too-many-rows", role=role, line=line)])
            if len(row) != len(header):
                raise InputError([issue("ragged-row", role=role, line=line)])
            rows.append(row)
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv", role=role)]) from exc
    if not rows:
        raise InputError([issue("no-data-rows", role=role)])
    return header, rows


def validate_token(value: str, *, role: str, field: str,
                   max_chars: int = MAX_ID_CHARS, allow_empty: bool = False) -> None:
    if not value and not allow_empty:
        raise InputError([issue("empty-value", role=role, field=field)])
    if value != value.strip():
        raise InputError([issue("surrounding-whitespace", role=role, field=field)])
    if len(value) > max_chars:
        raise InputError([issue("value-too-long", role=role, field=field)])
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputError([issue("control-character", role=role, field=field)])


def parse_feature_table(text: str) -> dict[str, Any]:
    role = "feature-table"
    header, rows = parse_tsv(text, role, MAX_FEATURES)
    if header[0] != "feature_id":
        raise InputError([issue("ambiguous-table-orientation", role=role,
                                field=header[0], value="first-header-must-be-feature_id")])
    sample_ids = header[1:]
    if not sample_ids:
        raise InputError([issue("no-sample-columns", role=role)])
    if len(sample_ids) > MAX_SAMPLES:
        raise InputError([issue("too-many-samples", role=role, value=len(sample_ids))])
    for sample_id in sample_ids:
        validate_token(sample_id, role=role, field="sample-id")
    if len(sample_ids) != len(set(sample_ids)):
        raise InputError([issue("duplicate-sample-id", role=role)])
    if len(rows) * len(sample_ids) > MAX_CELLS:
        raise InputError([issue("too-many-count-cells", role=role,
                                value=len(rows) * len(sample_ids))])

    seen_features: set[str] = set()
    sample_totals = {sample_id: 0 for sample_id in sample_ids}
    feature_totals: list[dict[str, Any]] = []
    zero_cells = 0
    for line, row in enumerate(rows, start=2):
        feature_id = row[0]
        validate_token(feature_id, role=role, field="feature-id")
        if feature_id in seen_features:
            raise InputError([issue("duplicate-feature-id", role=role, line=line,
                                    field="feature_id", value=feature_id)])
        seen_features.add(feature_id)
        feature_total = 0
        for sample_id, raw_count in zip(sample_ids, row[1:]):
            if not ASCII_INTEGER.fullmatch(raw_count):
                code = "negative-count" if raw_count.startswith("-") else "noninteger-count"
                raise InputError([issue(code, role=role, line=line,
                                        field=sample_id, value=raw_count)])
            significant = raw_count.lstrip("0") or "0"
            maximum = str(MAX_COUNT)
            if len(significant) > len(maximum) or (
                len(significant) == len(maximum) and significant > maximum
            ):
                raise InputError([issue("count-too-large", role=role, line=line,
                                        field=sample_id)])
            count = int(significant)
            if count > MAX_COUNT:
                raise InputError([issue("count-too-large", role=role, line=line,
                                        field=sample_id)])
            feature_total += count
            sample_totals[sample_id] += count
            zero_cells += count == 0
        feature_totals.append({"feature_id": feature_id, "total_count": feature_total})

    feature_totals.sort(key=lambda item: item["feature_id"])
    return {
        "feature_ids": seen_features,
        "sample_ids": set(sample_ids),
        "sample_totals": sample_totals,
        "feature_totals": feature_totals,
        "zero_cells": zero_cells,
        "total_cells": len(rows) * len(sample_ids),
    }


def parse_metadata(text: str, sample_column: str, control_column: str | None,
                   control_values: list[str]) -> dict[str, Any]:
    role = "metadata"
    header, rows = parse_tsv(text, role, MAX_METADATA_ROWS)
    validate_token(sample_column, role=role, field="metadata-sample-column")
    if sample_column not in header:
        raise InputError([issue("missing-sample-id-column", role=role,
                                field=sample_column)])
    if bool(control_column) != bool(control_values):
        raise InputError([issue("incomplete-negative-control-declaration", role=role)])
    if len(control_values) > MAX_NEGATIVE_CONTROL_VALUES:
        raise InputError([issue("too-many-negative-control-values", role=role)])
    if control_column is not None:
        validate_token(control_column, role=role, field="negative-control-column")
        if control_column not in header:
            raise InputError([issue("missing-negative-control-column", role=role,
                                    field=control_column)])
        if len(control_values) != len(set(control_values)):
            raise InputError([issue("duplicate-negative-control-value", role=role)])
        for value in control_values:
            validate_token(value, role=role, field="negative-control-value")

    sample_index = header.index(sample_column)
    control_index = header.index(control_column) if control_column is not None else None
    sample_ids: set[str] = set()
    negative_ids: set[str] = set()
    for line, row in enumerate(rows, start=2):
        sample_id = row[sample_index]
        validate_token(sample_id, role=role, field=sample_column)
        if sample_id in sample_ids:
            raise InputError([issue("duplicate-sample-id", role=role, line=line,
                                    field=sample_column, value=sample_id)])
        sample_ids.add(sample_id)
        if control_index is not None and row[control_index] in control_values:
            negative_ids.add(sample_id)
    return {"sample_ids": sample_ids, "negative_ids": negative_ids}


def parse_taxonomy(text: str, feature_ids: set[str]) -> dict[str, Any]:
    role = "taxonomy"
    header, rows = parse_tsv(text, role, MAX_FEATURES)
    if header[0] != "feature_id":
        raise InputError([issue("invalid-taxonomy-id-column", role=role,
                                field=header[0])])
    ranks = header[1:]
    if not ranks:
        raise InputError([issue("no-taxonomy-rank-columns", role=role)])
    if any(rank not in CANONICAL_RANKS for rank in ranks):
        raise InputError([issue("unsupported-taxonomy-rank", role=role)])
    expected_order = [rank for rank in CANONICAL_RANKS if rank in ranks]
    if ranks != expected_order:
        raise InputError([issue("taxonomy-ranks-not-in-canonical-order", role=role)])

    taxonomy_ids: set[str] = set()
    assigned = {rank: 0 for rank in ranks}
    for line, row in enumerate(rows, start=2):
        feature_id = row[0]
        validate_token(feature_id, role=role, field="feature_id")
        if feature_id in taxonomy_ids:
            raise InputError([issue("duplicate-taxonomy-feature-id", role=role,
                                    line=line, value=feature_id)])
        taxonomy_ids.add(feature_id)
        for rank, value in zip(ranks, row[1:]):
            validate_token(value, role=role, field=rank,
                           max_chars=MAX_TAXONOMY_VALUE_CHARS, allow_empty=True)
            assigned[rank] += bool(value)

    missing = sorted(feature_ids - taxonomy_ids)
    extra = sorted(taxonomy_ids - feature_ids)
    if missing or extra:
        raise InputError([issue("taxonomy-feature-id-mismatch", role=role,
                                value={"missing_count": len(missing),
                                       "extra_count": len(extra),
                                       "missing_examples": missing[:10],
                                       "extra_examples": extra[:10]})])
    total = len(feature_ids)
    return {
        "provided": True,
        "feature_count": total,
        "rank_completeness": [
            {
                "rank": rank,
                "assigned_features": assigned[rank],
                "unassigned_features": total - assigned[rank],
                "assigned_fraction": assigned[rank] / total,
            }
            for rank in ranks
        ],
    }


def fingerprint(payload: bytes) -> dict[str, Any]:
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def analyze(
    feature_payload: bytes,
    feature_text: str,
    metadata_payload: bytes,
    metadata_text: str,
    *,
    taxonomy_payload: bytes | None,
    taxonomy_text: str | None,
    metadata_sample_column: str,
    negative_control_column: str | None,
    negative_control_values: list[str],
) -> dict[str, Any]:
    feature = parse_feature_table(feature_text)
    metadata = parse_metadata(metadata_text, metadata_sample_column,
                              negative_control_column, negative_control_values)
    table_samples = feature["sample_ids"]
    metadata_samples = metadata["sample_ids"]
    matched = sorted(table_samples & metadata_samples)
    table_only = sorted(table_samples - metadata_samples)
    metadata_only = sorted(metadata_samples - table_samples)
    total_cells = feature["total_cells"]
    zero_cells = feature["zero_cells"]
    sample_totals = feature["sample_totals"]
    zero_depth = sorted(sample_id for sample_id, total in sample_totals.items() if total == 0)
    zero_total_features = [item["feature_id"] for item in feature["feature_totals"]
                           if item["total_count"] == 0]

    if taxonomy_payload is None:
        taxonomy_report: dict[str, Any] = {"provided": False}
        taxonomy_input = None
    else:
        if taxonomy_text is None:
            raise AssertionError("taxonomy bytes and text must be provided together")
        taxonomy_report = parse_taxonomy(taxonomy_text, feature["feature_ids"])
        taxonomy_input = fingerprint(taxonomy_payload)

    negative_ids = metadata["negative_ids"]
    joined_negative_ids = sorted(negative_ids & table_samples)
    if negative_control_column is None:
        negative_controls: dict[str, Any] = {"declared": False}
    else:
        negative_controls = {
            "declared": True,
            "metadata_column": negative_control_column,
            "declared_values": sorted(negative_control_values),
            "metadata_negative_control_count": len(negative_ids),
            "joined_negative_control_count": len(joined_negative_ids),
            "metadata_only_negative_control_ids": sorted(negative_ids - table_samples),
            "samples": [
                {
                    "sample_id": sample_id,
                    "library_size": sample_totals[sample_id],
                    "zero_depth": sample_totals[sample_id] == 0,
                }
                for sample_id in joined_negative_ids
            ],
            "interpretation": "descriptive-only-no-contamination-decision",
        }

    return {
        "schema_version": "1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": {"name": "qc_amplicon_tables", "version": VERSION},
        "inputs": {
            "feature_table": {**fingerprint(feature_payload),
                              "orientation": "feature-rows-by-sample-columns"},
            "metadata": {**fingerprint(metadata_payload),
                         "sample_id_column": metadata_sample_column},
            "taxonomy": taxonomy_input,
        },
        "limits": {
            "max_input_bytes_per_file": MAX_INPUT_BYTES,
            "max_features": MAX_FEATURES,
            "max_samples": MAX_SAMPLES,
            "max_metadata_rows": MAX_METADATA_ROWS,
            "max_count_cells": MAX_CELLS,
            "max_count_value": MAX_COUNT,
        },
        "joins": {
            "feature_table_sample_count": len(table_samples),
            "metadata_sample_count": len(metadata_samples),
            "matched_sample_count": len(matched),
            "matched_sample_ids": matched,
            "feature_table_only_sample_ids": table_only,
            "metadata_only_sample_ids": metadata_only,
        },
        "duplicate_ids": {
            "feature_ids": 0,
            "feature_table_sample_ids": 0,
            "metadata_sample_ids": 0,
            "taxonomy_feature_ids": 0 if taxonomy_payload is not None else None,
        },
        "sample_qc": {
            "library_sizes": [
                {"sample_id": sample_id, "library_size": sample_totals[sample_id]}
                for sample_id in sorted(sample_totals)
            ],
            "zero_depth_sample_count": len(zero_depth),
            "zero_depth_sample_ids": zero_depth,
        },
        "feature_qc": {
            "feature_count": len(feature["feature_ids"]),
            "feature_totals": feature["feature_totals"],
            "zero_total_feature_count": len(zero_total_features),
            "zero_total_feature_ids": zero_total_features,
        },
        "sparsity": {
            "total_cells": total_cells,
            "zero_cells": zero_cells,
            "nonzero_cells": total_cells - zero_cells,
            "zero_fraction": zero_cells / total_cells,
            "missing_count_cells": 0,
        },
        "taxonomy_qc": taxonomy_report,
        "negative_controls": negative_controls,
        "limitations": [
            "Observed zeros are preserved; missing count cells are invalid input.",
            "Counts are descriptive and are not normalized, rarefied, imputed, or tested.",
            "Taxonomy is caller-supplied and is not assigned or biologically validated.",
            "Negative-control summaries do not establish contamination or pathogen status.",
        ],
    }


def output_target(path: Path, root: Path | None = None) -> tuple[Path, Path, tuple[str, ...]]:
    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    try:
        root_state = os.lstat(lexical_root)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"output root does not exist: {lexical_root}") from exc
    if stat.S_ISLNK(root_state.st_mode):
        raise PermissionError(f"output root is a symlink: {lexical_root}")
    if not stat.S_ISDIR(root_state.st_mode):
        raise NotADirectoryError(lexical_root)
    if ".." in path.parts:
        raise PermissionError(f"output path contains parent traversal: {path}")
    if path.is_absolute():
        candidate = Path(os.path.abspath(path))
    else:
        candidate = lexical_root / path
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise PermissionError(f"output is outside the allowed root: {candidate}") from exc
    if not relative.parts:
        raise IsADirectoryError(candidate)
    return lexical_root, candidate, relative.parts


def open_output_parent(path: Path, root: Path | None = None) -> tuple[Path, int, str]:
    lexical_root, candidate, parts = output_target(path, root)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lexical_root, flags)
    except OSError as exc:
        raise PermissionError(f"output root changed or is unsafe: {lexical_root}") from exc
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                raise FileNotFoundError(f"output parent does not exist: {candidate.parent}") from exc
            except OSError as exc:
                raise PermissionError(f"output parent changed or is unsafe: {candidate.parent}") from exc
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


def write_new(
    path: Path,
    text: str,
    *,
    root: Path | None = None,
    before_publish: Callable[[], None] | None = None,
) -> Path:
    target, directory_fd, target_name = open_output_parent(path, root)
    temporary_name = f".{target_name}.tmp-{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: tuple[int, int] | None = None
    published = False
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
        if before_publish is not None:
            before_publish()
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
        # The hard link is the commit point. Post-commit cleanup is best-effort:
        # returning an error after publication would misreport a valid artifact.
        try:
            unlink_owned_at(temporary_name, directory_fd, identity)
            os.fsync(directory_fd)
        except OSError:
            pass
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None and not published:
            unlink_owned_at(temporary_name, directory_fd, identity)
        raise
    finally:
        os.close(directory_fd)
    return target


def expect_issue(code: str, action: Callable[[], Any]) -> None:
    try:
        action()
    except InputError as exc:
        if not exc.issues or exc.issues[0]["code"] != code:
            raise RuntimeError(f"expected {code}, got {exc.issues}") from exc
    else:
        raise AssertionError(f"{code} input was accepted")


def self_test() -> None:
    feature_text = (
        "feature_id\tS1\tS2\tNC1\tS4\n"
        "ASV1\t10\t0\t0\t3\n"
        "ASV2\t0\t5\t0\t0\n"
        "ASV3\t1\t0\t0\t2\n"
        "ASV4\t0\t0\t0\t0\n"
    )
    metadata_text = (
        "sample_id\tgroup\tsample_type\n"
        "S1\tA\tsample\nS2\tA\tsample\nNC1\tB\tnegative\nS4\tB\tsample\n"
    )
    taxonomy_text = (
        "feature_id\tdomain\tphylum\tgenus\n"
        "ASV1\tBacteria\tFirmicutes\tLactobacillus\n"
        "ASV2\tBacteria\tBacteroidota\tBacteroides\n"
        "ASV3\tBacteria\tProteobacteria\t\n"
        "ASV4\t\t\t\n"
    )
    arguments = {
        "taxonomy_payload": taxonomy_text.encode(),
        "taxonomy_text": taxonomy_text,
        "metadata_sample_column": "sample_id",
        "negative_control_column": "sample_type",
        "negative_control_values": ["negative"],
    }
    report = analyze(feature_text.encode(), feature_text,
                     metadata_text.encode(), metadata_text, **arguments)
    if report["sample_qc"]["zero_depth_sample_ids"] != ["NC1"]:
        raise RuntimeError("zero-depth sample self-test differs")
    if report["sparsity"] != {
        "total_cells": 16,
        "zero_cells": 11,
        "nonzero_cells": 5,
        "zero_fraction": 11 / 16,
        "missing_count_cells": 0,
    }:
        raise RuntimeError("sparsity self-test differs")
    totals = {item["feature_id"]: item["total_count"]
              for item in report["feature_qc"]["feature_totals"]}
    if totals != {"ASV1": 13, "ASV2": 5, "ASV3": 3, "ASV4": 0}:
        raise RuntimeError("feature-total self-test differs")
    completeness = {item["rank"]: item["assigned_features"]
                    for item in report["taxonomy_qc"]["rank_completeness"]}
    if completeness != {"domain": 3, "phylum": 3, "genus": 2}:
        raise RuntimeError("taxonomy completeness self-test differs")
    if report["negative_controls"]["samples"] != [
        {"sample_id": "NC1", "library_size": 0, "zero_depth": True}
    ]:
        raise RuntimeError("negative-control self-test differs")
    second = analyze(feature_text.encode(), feature_text,
                     metadata_text.encode(), metadata_text, **arguments)
    if json.dumps(report, sort_keys=True) != json.dumps(second, sort_keys=True):
        raise RuntimeError("deterministic report self-test differs")

    expect_issue("negative-count", lambda: parse_feature_table(
        "feature_id\tS1\nASV1\t-1\n"))
    expect_issue("noninteger-count", lambda: parse_feature_table(
        "feature_id\tS1\nASV1\t1.5\n"))
    expect_issue("count-too-large", lambda: parse_feature_table(
        "feature_id\tS1\nASV1\t" + ("9" * 5000) + "\n"))
    padded_zero = parse_feature_table(
        "feature_id\tS1\nASV1\t" + ("0" * 5000) + "\n")
    if padded_zero["sample_totals"] != {"S1": 0}:
        raise RuntimeError("leading-zero count self-test differs")
    expect_issue("duplicate-header", lambda: parse_feature_table(
        "feature_id\tS1\tS1\nASV1\t1\t2\n"))
    expect_issue("ambiguous-table-orientation", lambda: parse_feature_table(
        "sample_id\tASV1\nS1\t1\n"))
    expect_issue("duplicate-sample-id", lambda: parse_metadata(
        "sample_id\tgroup\nS1\tA\nS1\tB\n", "sample_id", None, []))
    expect_issue("taxonomy-feature-id-mismatch", lambda: parse_taxonomy(
        "feature_id\tdomain\nASV1\tBacteria\nASV5\tBacteria\n",
        {"ASV1", "ASV2"}))
    expect_issue("incomplete-negative-control-declaration", lambda: parse_metadata(
        metadata_text, "sample_id", "sample_type", []))

    with tempfile.TemporaryDirectory(prefix="amplicon-qc-selftest-") as temporary_name:
        root = Path(temporary_name)
        regular = root / "feature.tsv"
        regular.write_text(feature_text, encoding="utf-8")
        payload, text = read_local_file(regular, "feature-table")
        if payload != feature_text.encode() or text != feature_text:
            raise RuntimeError("regular input self-test differs")
        linked_input = root / "linked.tsv"
        linked_input.symlink_to(regular)
        expect_issue("input-not-regular-file",
                     lambda: read_local_file(linked_input, "feature-table"))

        output = root / "report.json"
        write_new(output, "{}\n", root=root)
        try:
            write_new(output, "replacement\n", root=root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output was replaced")
        if output.read_text(encoding="utf-8") != "{}\n":
            raise RuntimeError("no-overwrite self-test differs")
        try:
            write_new(Path("..") / "escape.json", "{}\n", root=root)
        except PermissionError:
            pass
        else:
            raise AssertionError("parent traversal output was accepted")

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        try:
            write_new(Path("linked-parent") / "report.json", "{}\n", root=root)
        except PermissionError:
            pass
        else:
            raise AssertionError("symlinked output parent was accepted")

        swap_parent = root / "swap-parent"
        swap_parent.mkdir()
        held_parent = root / "held-parent"
        with tempfile.TemporaryDirectory(prefix="amplicon-qc-outside-") as outside_name:
            outside = Path(outside_name)

            def swap_output_parent() -> None:
                swap_parent.rename(held_parent)
                swap_parent.symlink_to(outside, target_is_directory=True)

            write_new(
                Path("swap-parent") / "report.json",
                "{}\n",
                root=root,
                before_publish=swap_output_parent,
            )
            if (outside / "report.json").exists():
                raise RuntimeError("output-parent swap escaped the allowed directory")
            if not (held_parent / "report.json").is_file():
                raise RuntimeError("held output-parent publication self-test differs")
            swap_parent.unlink()
            held_parent.rename(swap_parent)

        fsync_output = root / "fsync-report.json"
        real_fsync = os.fsync

        def fail_directory_fsync(descriptor: int) -> None:
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("injected directory fsync failure")
            real_fsync(descriptor)

        os.fsync = fail_directory_fsync
        try:
            write_new(fsync_output, "{}\n", root=root)
        finally:
            os.fsync = real_fsync
        if fsync_output.read_text(encoding="utf-8") != "{}\n":
            raise RuntimeError("post-commit fsync self-test differs")

    print(json.dumps({"checks": 19, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--feature-table", type=Path)
    result.add_argument("--metadata", type=Path)
    result.add_argument("--taxonomy", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--metadata-sample-column", default="sample_id")
    result.add_argument("--negative-control-column")
    result.add_argument("--negative-control-value", action="append", default=[])
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    missing = [name for name in ("feature_table", "metadata", "output")
               if getattr(args, name) is None]
    if missing:
        parser().error("required for execution: " + ", ".join(
            f"--{name.replace('_', '-')}" for name in missing
        ))
    try:
        feature_payload, feature_text = read_local_file(args.feature_table, "feature-table")
        metadata_payload, metadata_text = read_local_file(args.metadata, "metadata")
        taxonomy_payload: bytes | None = None
        taxonomy_text: str | None = None
        if args.taxonomy is not None:
            taxonomy_payload, taxonomy_text = read_local_file(args.taxonomy, "taxonomy")
        report = analyze(
            feature_payload,
            feature_text,
            metadata_payload,
            metadata_text,
            taxonomy_payload=taxonomy_payload,
            taxonomy_text=taxonomy_text,
            metadata_sample_column=args.metadata_sample_column,
            negative_control_column=args.negative_control_column,
            negative_control_values=args.negative_control_value,
        )
        rendered = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
        write_new(args.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "features": report["feature_qc"]["feature_count"],
            "output": str(args.output),
            "samples": report["joins"]["feature_table_sample_count"],
            "status": "completed",
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
