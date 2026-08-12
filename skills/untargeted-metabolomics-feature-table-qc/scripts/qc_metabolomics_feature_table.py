#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded descriptive QC report for a metabolomics feature table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import stat
import statistics
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
MAX_NUMBER_CHARS = 128
INTENSITY_SEMANTICS = (
    "raw-peak-area",
    "raw-peak-height",
    "processed-nonnegative-abundance",
)
SAMPLE_TYPES = ("study", "pooled_qc", "blank")
ZERO_SEMANTICS = ("observed", "missing")
ASCII_INTEGER = re.compile(r"[0-9]+\Z")


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


def validate_token(
    value: str,
    *,
    role: str,
    field: str,
    max_chars: int = MAX_ID_CHARS,
    allow_empty: bool = False,
) -> None:
    if not value and not allow_empty:
        raise InputError([issue("empty-value", role=role, field=field)])
    if value != value.strip():
        raise InputError([issue("surrounding-whitespace", role=role, field=field)])
    if len(value) > max_chars:
        raise InputError([issue("value-too-long", role=role, field=field)])
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputError([issue("control-character", role=role, field=field)])


def validate_missing_token(value: str) -> None:
    validate_token(value, role="declaration", field="missing-token")
    try:
        float(value)
    except ValueError:
        return
    raise InputError([issue("missing-token-must-be-nonnumeric", role="declaration",
                            field="missing-token")])


def read_local_file(path: Path, role: str, *, root: Path | None = None) -> tuple[bytes, str]:
    """Read one stable, regular, non-symlink UTF-8 file within the byte cap."""
    supplied = Path(path)
    if ".." in supplied.parts:
        raise InputError([issue("parent-traversal", role=role)])
    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    try:
        root_state = os.lstat(lexical_root)
        if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
            raise InputError([issue("unsafe-working-directory", role=role)])
        candidate = Path(os.path.abspath(
            supplied if supplied.is_absolute() else lexical_root / supplied
        ))
        try:
            relative = candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise InputError([issue("path-outside-working-directory", role=role)]) from exc
        if not relative.parts:
            raise InputError([issue("input-not-regular-file", role=role)])

        directory_flags = (
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_fd = os.open(lexical_root, directory_flags)
        try:
            opened_root = os.fstat(parent_fd)
            if (opened_root.st_dev, opened_root.st_ino) != (root_state.st_dev, root_state.st_ino):
                raise InputError([issue("unsafe-working-directory", role=role)])
            for part in relative.parts[:-1]:
                try:
                    child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                except OSError as exc:
                    raise InputError([issue("input-parent-symlink", role=role)]) from exc
                os.close(parent_fd)
                parent_fd = child_fd

            name = relative.parts[-1]
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except BaseException:
            os.close(parent_fd)
            parent_fd = -1
            raise
        if not stat.S_ISREG(before.st_mode):
            raise InputError([issue("input-not-regular-file", role=role)])
        if before.st_size > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large", role=role)])

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, dir_fd=parent_fd)
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

        after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        os.close(parent_fd)
        parent_fd = -1
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
    finally:
        if "parent_fd" in locals() and parent_fd >= 0:
            os.close(parent_fd)


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
        validate_token(field, role=role, field="header")

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


def parse_number(raw: str, *, role: str, line: int, field: str) -> float:
    validate_token(raw, role=role, field=field, max_chars=MAX_NUMBER_CHARS)
    try:
        value = float(raw)
    except ValueError as exc:
        raise InputError([issue(f"invalid-{field}", role=role, line=line,
                                field=field, value=raw)]) from exc
    if not math.isfinite(value):
        raise InputError([issue(f"nonfinite-{field}", role=role, line=line,
                                field=field, value=raw)])
    return value


def parse_intensity(raw: str, *, line: int, sample_id: str,
                    missing_token: str) -> float | None:
    if raw == missing_token:
        return None
    value = parse_number(raw, role="feature-table", line=line, field="intensity")
    if value < 0:
        raise InputError([issue("negative-intensity", role="feature-table", line=line,
                                field=sample_id, value=raw)])
    return value


def parse_feature_table(text: str, missing_token: str,
                        zero_semantics: str) -> dict[str, Any]:
    role = "feature-table"
    header, rows = parse_tsv(text, role, MAX_FEATURES)
    expected = ["feature_id", "mz", "retention_time_seconds"]
    if header[:3] != expected:
        raise InputError([issue("ambiguous-table-orientation", role=role,
                                value="first-headers-must-be-feature_id,mz,retention_time_seconds")])
    sample_ids = header[3:]
    if not sample_ids:
        raise InputError([issue("no-sample-columns", role=role)])
    if len(sample_ids) > MAX_SAMPLES:
        raise InputError([issue("too-many-samples", role=role, value=len(sample_ids))])
    for sample_id in sample_ids:
        validate_token(sample_id, role=role, field="sample-id")
    if len(rows) * len(sample_ids) > MAX_CELLS:
        raise InputError([issue("too-many-intensity-cells", role=role,
                                value=len(rows) * len(sample_ids))])

    sample_counts = {
        sample_id: {"detected_feature_count": 0, "missing_token_count": 0,
                    "zero_as_missing_count": 0}
        for sample_id in sample_ids
    }
    features: list[dict[str, Any]] = []
    seen_features: set[str] = set()
    for line, row in enumerate(rows, start=2):
        feature_id = row[0]
        validate_token(feature_id, role=role, field="feature-id")
        if feature_id in seen_features:
            raise InputError([issue("duplicate-feature-id", role=role, line=line,
                                    field="feature_id", value=feature_id)])
        seen_features.add(feature_id)

        mz = parse_number(row[1], role=role, line=line, field="mz")
        if mz <= 0:
            raise InputError([issue("nonpositive-mz", role=role, line=line,
                                    field="mz", value=row[1])])
        retention_time = parse_number(row[2], role=role, line=line,
                                      field="retention-time-seconds")
        if retention_time < 0:
            raise InputError([issue("negative-retention-time-seconds", role=role,
                                    line=line, field="retention_time_seconds",
                                    value=row[2])])

        values: dict[str, float | None] = {}
        for sample_id, raw in zip(sample_ids, row[3:]):
            value = parse_intensity(raw, line=line, sample_id=sample_id,
                                    missing_token=missing_token)
            if value is None:
                sample_counts[sample_id]["missing_token_count"] += 1
                values[sample_id] = None
            elif value == 0 and zero_semantics == "missing":
                sample_counts[sample_id]["zero_as_missing_count"] += 1
                values[sample_id] = None
            else:
                sample_counts[sample_id]["detected_feature_count"] += 1
                values[sample_id] = value
        features.append({"feature_id": feature_id, "mz": mz,
                         "retention_time_seconds": retention_time, "values": values})

    features.sort(key=lambda item: item["feature_id"])
    return {"sample_ids": set(sample_ids), "features": features,
            "sample_counts": sample_counts, "cell_count": len(rows) * len(sample_ids)}


def parse_metadata(text: str) -> dict[str, Any]:
    role = "metadata"
    header, rows = parse_tsv(text, role, MAX_METADATA_ROWS)
    expected = ["sample_id", "sample_type", "batch", "injection_order"]
    if header != expected:
        raise InputError([issue("invalid-metadata-header", role=role, value=expected)])

    records: dict[str, dict[str, Any]] = {}
    for line, row in enumerate(rows, start=2):
        sample_id, sample_type, batch, raw_order = row
        validate_token(sample_id, role=role, field="sample_id")
        if sample_id in records:
            raise InputError([issue("duplicate-sample-id", role=role, line=line,
                                    field="sample_id", value=sample_id)])
        if sample_type not in SAMPLE_TYPES:
            raise InputError([issue("invalid-sample-type", role=role, line=line,
                                    field="sample_type", value=sample_type)])
        validate_token(batch, role=role, field="batch", allow_empty=True)
        if raw_order:
            validate_token(raw_order, role=role, field="injection_order",
                           max_chars=MAX_NUMBER_CHARS)
            if not ASCII_INTEGER.fullmatch(raw_order) or int(raw_order) < 1:
                raise InputError([issue("invalid-injection-order", role=role, line=line,
                                        field="injection_order", value=raw_order)])
            injection_order: int | None = int(raw_order)
        else:
            injection_order = None
        records[sample_id] = {"sample_type": sample_type, "batch": batch or None,
                              "injection_order": injection_order}
    return {"sample_ids": set(records), "records": records}


def fingerprint(payload: bytes) -> dict[str, Any]:
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def pooled_qc_rsd(values: list[float], declared_count: int) -> dict[str, Any]:
    if declared_count == 0:
        return {"status": "not-estimable", "reason": "no-pooled-qc-samples",
                "usable_value_count": 0}
    if len(values) < 2:
        return {"status": "not-estimable", "reason": "fewer-than-two-usable-values",
                "usable_value_count": len(values)}
    try:
        mean = statistics.fmean(values)
        standard_deviation = statistics.stdev(values)
    except OverflowError:
        return {"status": "not-estimable", "reason": "numeric-range-overflow",
                "usable_value_count": len(values)}
    if not math.isfinite(mean) or not math.isfinite(standard_deviation):
        return {"status": "not-estimable", "reason": "numeric-range-overflow",
                "usable_value_count": len(values)}
    if mean == 0:
        return {"status": "not-estimable", "reason": "mean-is-zero",
                "usable_value_count": len(values)}
    rsd_percent = standard_deviation / mean * 100
    if not math.isfinite(rsd_percent):
        return {"status": "not-estimable", "reason": "numeric-range-overflow",
                "usable_value_count": len(values)}
    return {"status": "estimated", "usable_value_count": len(values), "mean": mean,
            "sample_standard_deviation": standard_deviation,
            "rsd_percent": rsd_percent}


def blank_to_study_ratio(blank_values: list[float], study_values: list[float],
                         blank_count: int, study_count: int) -> dict[str, Any]:
    if blank_count == 0:
        reason = "no-blank-samples"
    elif study_count == 0:
        reason = "no-study-samples"
    elif not blank_values:
        reason = "no-usable-blank-values"
    elif not study_values:
        reason = "no-usable-study-values"
    else:
        try:
            blank_mean = statistics.fmean(blank_values)
            study_mean = statistics.fmean(study_values)
        except OverflowError:
            reason = "numeric-range-overflow"
            return {"status": "not-estimable", "reason": reason,
                    "blank_usable_value_count": len(blank_values),
                    "study_usable_value_count": len(study_values)}
        if study_mean != 0:
            ratio = blank_mean / study_mean
            if not math.isfinite(ratio):
                return {"status": "not-estimable", "reason": "numeric-range-overflow",
                        "blank_usable_value_count": len(blank_values),
                        "study_usable_value_count": len(study_values)}
            return {"status": "estimated", "blank_usable_value_count": len(blank_values),
                    "study_usable_value_count": len(study_values),
                    "blank_mean": blank_mean, "study_mean": study_mean,
                    "blank_to_study_mean_ratio": ratio}
        reason = "study-mean-is-zero"
    return {"status": "not-estimable", "reason": reason,
            "blank_usable_value_count": len(blank_values),
            "study_usable_value_count": len(study_values)}


def analyze(
    feature_payload: bytes,
    feature_text: str,
    metadata_payload: bytes,
    metadata_text: str,
    *,
    intensity_semantics: str,
    missing_token: str,
    zero_semantics: str,
) -> dict[str, Any]:
    if intensity_semantics not in INTENSITY_SEMANTICS:
        raise InputError([issue("invalid-intensity-semantics", role="declaration")])
    if zero_semantics not in ZERO_SEMANTICS:
        raise InputError([issue("invalid-zero-semantics", role="declaration")])
    validate_missing_token(missing_token)
    feature = parse_feature_table(feature_text, missing_token, zero_semantics)
    metadata = parse_metadata(metadata_text)
    table_samples = feature["sample_ids"]
    metadata_samples = metadata["sample_ids"]
    if table_samples != metadata_samples:
        table_only = sorted(table_samples - metadata_samples)
        metadata_only = sorted(metadata_samples - table_samples)
        raise InputError([issue("sample-id-mismatch", role="join", value={
            "feature_table_only_count": len(table_only),
            "metadata_only_count": len(metadata_only),
            "feature_table_only_examples": table_only[:10],
            "metadata_only_examples": metadata_only[:10],
        })])

    records = metadata["records"]
    samples_by_type = {
        sample_type: sorted(sample_id for sample_id, record in records.items()
                            if record["sample_type"] == sample_type)
        for sample_type in SAMPLE_TYPES
    }
    feature_reports: list[dict[str, Any]] = []
    for feature_row in feature["features"]:
        values = feature_row["values"]
        pooled_values = [values[sample_id] for sample_id in samples_by_type["pooled_qc"]
                         if values[sample_id] is not None]
        blank_values = [values[sample_id] for sample_id in samples_by_type["blank"]
                        if values[sample_id] is not None]
        study_values = [values[sample_id] for sample_id in samples_by_type["study"]
                        if values[sample_id] is not None]
        feature_reports.append({
            "feature_id": feature_row["feature_id"],
            "mz": feature_row["mz"],
            "retention_time_seconds": feature_row["retention_time_seconds"],
            "pooled_qc_rsd": pooled_qc_rsd(pooled_values,
                                            len(samples_by_type["pooled_qc"])),
            "blank_to_study": blank_to_study_ratio(
                blank_values, study_values, len(samples_by_type["blank"]),
                len(samples_by_type["study"])),
        })

    batch_missing = sorted(sample_id for sample_id, record in records.items()
                           if record["batch"] is None)
    order_missing = sorted(sample_id for sample_id, record in records.items()
                           if record["injection_order"] is None)
    positions: dict[tuple[str | None, int], list[str]] = {}
    for sample_id, record in records.items():
        if record["injection_order"] is not None:
            key = (record["batch"], record["injection_order"])
            positions.setdefault(key, []).append(sample_id)
    duplicate_positions = [
        {"batch": batch, "injection_order": order, "sample_ids": sorted(sample_ids)}
        for (batch, order), sample_ids in positions.items() if len(sample_ids) > 1
    ]
    duplicate_positions.sort(key=lambda item: (
        "" if item["batch"] is None else item["batch"], item["injection_order"]))

    sample_reports = []
    for sample_id in sorted(table_samples):
        counts = feature["sample_counts"][sample_id]
        total_missing = counts["missing_token_count"] + counts["zero_as_missing_count"]
        sample_reports.append({"sample_id": sample_id,
                               "sample_type": records[sample_id]["sample_type"],
                               **counts, "total_missing_feature_count": total_missing})

    return {
        "schema_version": "1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": {"name": "qc_metabolomics_feature_table", "version": VERSION},
        "inputs": {
            "feature_table": {**fingerprint(feature_payload),
                              "orientation": "feature-rows-by-sample-columns"},
            "metadata": fingerprint(metadata_payload),
            "declarations": {"intensity_semantics": intensity_semantics,
                             "missing_token": missing_token,
                             "zero_semantics": zero_semantics},
        },
        "limits": {"max_input_bytes_per_file": MAX_INPUT_BYTES,
                   "max_features": MAX_FEATURES, "max_samples": MAX_SAMPLES,
                   "max_metadata_rows": MAX_METADATA_ROWS,
                   "max_intensity_cells": MAX_CELLS},
        "joins": {"exact": True, "feature_table_sample_count": len(table_samples),
                  "metadata_sample_count": len(metadata_samples),
                  "matched_sample_count": len(table_samples),
                  "feature_table_only_sample_ids": [], "metadata_only_sample_ids": []},
        "duplicate_ids": {"feature_ids": 0, "feature_table_sample_ids": 0,
                          "metadata_sample_ids": 0},
        "sample_qc": sample_reports,
        "feature_qc": {"feature_count": len(feature["features"]),
                       "intensity_cell_count": feature["cell_count"],
                       "features": feature_reports},
        "metadata_qc": {
            "sample_type_counts": {sample_type: len(samples_by_type[sample_type])
                                   for sample_type in SAMPLE_TYPES},
            "batch_completeness": {"present_count": len(records) - len(batch_missing),
                                   "missing_count": len(batch_missing),
                                   "missing_sample_ids": batch_missing},
            "injection_order_completeness": {
                "present_count": len(records) - len(order_missing),
                "missing_count": len(order_missing), "missing_sample_ids": order_missing},
            "duplicate_injection_positions": duplicate_positions,
        },
        "limitations": [
            "Intensity, zero, missing-value, sample-type, batch, and injection-order semantics are caller declarations.",
            "RSD and blank-to-study ratios are descriptive and are not pass, contamination, carryover, or exclusion decisions.",
            "No peak picking, alignment, drift correction, filtering, normalization, imputation, annotation, differential testing, or pathway analysis was performed.",
        ],
    }


def output_target(
    path: Path, root: Path | None = None,
) -> tuple[Path, Path, tuple[str, ...], os.stat_result]:
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
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lexical_root, flags)
    except OSError as exc:
        raise PermissionError(f"output root changed or is unsafe: {lexical_root}") from exc
    opened_root = os.fstat(descriptor)
    if (opened_root.st_dev, opened_root.st_ino) != (root_state.st_dev, root_state.st_ino):
        os.close(descriptor)
        raise PermissionError(f"output root changed or is unsafe: {lexical_root}")
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


def write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def write_new(path: Path, text: str, *, root: Path | None = None,
              before_publish: Callable[[], None] | None = None) -> Path:
    target, directory_fd, target_name = open_output_parent(path, root)
    payload = text.encode("utf-8")
    temporary_name = f".{target_name}.tmp-{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: tuple[int, int] | None = None
    temporary_created = False
    temporary_present = False
    published = False
    original_error: BaseException | None = None
    cleanup_failures: list[str] = []
    try:
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        temporary_present = True
        write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if before_publish is not None:
            before_publish()
        try:
            os.link(temporary_name, target_name, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError as exc:
            raise FileExistsError(target) from exc
        published = True
        published_state = os.stat(
            target_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (published_state.st_dev, published_state.st_ino) != identity:
            raise OSError("published output identity differs from staged data")
        if not unlink_owned_at(temporary_name, directory_fd, identity):
            raise OSError("staged output identity changed before cleanup")
        temporary_present = False
        os.fsync(directory_fd)
        final_state = os.stat(
            target_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (final_state.st_dev, final_state.st_ino) != identity:
            raise OSError("published output identity changed before completion")
    except BaseException as exc:
        original_error = exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_failures.append(f"descriptor:{exc.__class__.__name__}")
        if original_error is not None:
            if temporary_created and identity is None:
                cleanup_failures.append("staged:identity-unavailable")
            if published and identity is not None:
                try:
                    if not unlink_owned_at(target_name, directory_fd, identity):
                        cleanup_failures.append("published:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"published:{exc.__class__.__name__}")
            if temporary_present and identity is not None:
                try:
                    if not unlink_owned_at(temporary_name, directory_fd, identity):
                        cleanup_failures.append("staged:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"staged:{exc.__class__.__name__}")
            if temporary_created:
                try:
                    os.fsync(directory_fd)
                except OSError as exc:
                    cleanup_failures.append(f"directory:{exc.__class__.__name__}")
        os.close(directory_fd)
    if cleanup_failures:
        raise OSError(
            "publication-rollback-failed: " + ", ".join(cleanup_failures)
        ) from original_error
    if original_error is not None:
        raise original_error
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

    feature_text = (
        "feature_id\tmz\tretention_time_seconds\tS1\tS2\tS3\tQC1\tQC2\tQC3\tB1\tB2\tB3\n"
        "F1\t100.1\t60\t100\t200\t300\t100\t100\t100\t10\t20\t30\n"
        "F2\t200.2\t120\t0\t0\t0\t10\t20\tNA\t0\t5\tNA\n"
        "F3\t300.3\t180\t10\tNA\t30\t0\t0\t0\t1\t2\t3\n"
        "F4\t400.4\t240\t10\t10\t10\t5\tNA\tNA\tNA\tNA\tNA\n"
        "F5\t500.5\t300\t0\t0\t0\t0\t0\t0\t0\t0\t0\n"
    )
    metadata_text = (
        "sample_id\tsample_type\tbatch\tinjection_order\n"
        "S1\tstudy\tbatch-1\t1\nS2\tstudy\tbatch-1\t2\nS3\tstudy\t\t\n"
        "QC1\tpooled_qc\tbatch-1\t3\nQC2\tpooled_qc\tbatch-1\t4\n"
        "QC3\tpooled_qc\tbatch-2\t1\nB1\tblank\tbatch-1\t5\n"
        "B2\tblank\tbatch-1\t5\nB3\tblank\tbatch-2\t\n"
    )
    arguments = {"intensity_semantics": "raw-peak-area", "missing_token": "NA",
                 "zero_semantics": "missing"}
    report = analyze(feature_text.encode(), feature_text,
                     metadata_text.encode(), metadata_text, **arguments)
    check(report["joins"]["matched_sample_count"] == 9, "join count differs")
    check(report["feature_qc"]["feature_count"] == 5, "feature count differs")
    sample_qc = {item["sample_id"]: item for item in report["sample_qc"]}
    check(sample_qc["S2"]["detected_feature_count"] == 2 and
          sample_qc["S2"]["total_missing_feature_count"] == 3,
          "sample missing counts differ")
    features = {item["feature_id"]: item for item in report["feature_qc"]["features"]}
    check(features["F1"]["pooled_qc_rsd"]["rsd_percent"] == 0,
          "pooled-QC zero RSD differs")
    check(math.isclose(features["F2"]["pooled_qc_rsd"]["rsd_percent"],
                       47.14045207910317), "pooled-QC RSD differs")
    check(features["F3"]["pooled_qc_rsd"]["reason"] ==
          "fewer-than-two-usable-values", "RSD not-estimable reason differs")
    check(math.isclose(features["F1"]["blank_to_study"][
        "blank_to_study_mean_ratio"], 0.1), "blank/study ratio differs")
    check(features["F4"]["blank_to_study"]["reason"] ==
          "no-usable-blank-values", "blank/study not-estimable reason differs")
    check(report["metadata_qc"]["batch_completeness"]["missing_sample_ids"] == ["S3"],
          "batch completeness differs")
    check(report["metadata_qc"]["injection_order_completeness"][
        "missing_sample_ids"] == ["B3", "S3"], "injection completeness differs")
    check(report["metadata_qc"]["duplicate_injection_positions"] == [{
        "batch": "batch-1", "injection_order": 5, "sample_ids": ["B1", "B2"]}],
        "duplicate injection positions differ")
    extreme_feature = (
        "feature_id\tmz\tretention_time_seconds\tS1\tB1\n"
        "F1\t100\t1\t1e-308\t1e308\n"
    )
    extreme_metadata = (
        "sample_id\tsample_type\tbatch\tinjection_order\n"
        "S1\tstudy\tb1\t1\nB1\tblank\tb1\t2\n"
    )
    extreme_report = analyze(
        extreme_feature.encode(), extreme_feature,
        extreme_metadata.encode(), extreme_metadata, **arguments,
    )
    extreme_ratio = extreme_report["feature_qc"]["features"][0]["blank_to_study"]
    check(
        extreme_ratio == {
            "status": "not-estimable",
            "reason": "numeric-range-overflow",
            "blank_usable_value_count": 1,
            "study_usable_value_count": 1,
        },
        "extreme finite blank/study ratio did not remain structured",
    )
    repeat = analyze(feature_text.encode(), feature_text,
                     metadata_text.encode(), metadata_text, **arguments)
    check(json.dumps(report, allow_nan=False, sort_keys=True) ==
          json.dumps(repeat, allow_nan=False, sort_keys=True), "determinism differs")

    observed = analyze(feature_text.encode(), feature_text,
                       metadata_text.encode(), metadata_text,
                       intensity_semantics="raw-peak-area", missing_token="NA",
                       zero_semantics="observed")
    observed_samples = {item["sample_id"]: item for item in observed["sample_qc"]}
    check(observed_samples["S2"]["detected_feature_count"] == 4 and
          observed_samples["S2"]["zero_as_missing_count"] == 0,
          "observed-zero semantics differ")

    expect_issue("negative-intensity", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\t1\t-1\n", "NA", "missing"))
    expect_issue("nonfinite-intensity", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\t1\tNaN\n", "NA", "missing"))
    expect_issue("nonfinite-intensity", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\t1\tInf\n", "NA", "missing"))
    expect_issue("duplicate-feature-id", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\t1\t1\nF1\t101\t2\t2\n",
        "NA", "missing"))
    expect_issue("duplicate-header", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\tS1\nF1\t100\t1\t1\t2\n",
        "NA", "missing"))
    expect_issue("ambiguous-table-orientation", lambda: parse_feature_table(
        "sample_id\tmz\tretention_time_seconds\tF1\nS1\t100\t1\t1\n", "NA", "missing"))
    expect_issue("nonpositive-mz", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t0\t1\t1\n", "NA", "missing"))
    expect_issue("nonfinite-mz", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\tNaN\t1\t1\n", "NA", "missing"))
    expect_issue("negative-retention-time-seconds", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\t-1\t1\n", "NA", "missing"))
    expect_issue("nonfinite-retention-time-seconds", lambda: parse_feature_table(
        "feature_id\tmz\tretention_time_seconds\tS1\nF1\t100\tInf\t1\n", "NA", "missing"))
    expect_issue("duplicate-sample-id", lambda: parse_metadata(
        "sample_id\tsample_type\tbatch\tinjection_order\nS1\tstudy\tb1\t1\nS1\tblank\tb1\t2\n"))
    expect_issue("invalid-sample-type", lambda: parse_metadata(
        "sample_id\tsample_type\tbatch\tinjection_order\nS1\tunknown\tb1\t1\n"))
    expect_issue("invalid-injection-order", lambda: parse_metadata(
        "sample_id\tsample_type\tbatch\tinjection_order\nS1\tstudy\tb1\t0\n"))
    expect_issue("missing-token-must-be-nonnumeric", lambda: validate_missing_token("0"))
    expect_issue("sample-id-mismatch", lambda: analyze(
        feature_text.encode(), feature_text,
        metadata_text.replace("B3\tblank", "B4\tblank").encode(),
        metadata_text.replace("B3\tblank", "B4\tblank"), **arguments))

    with tempfile.TemporaryDirectory(prefix="metabolomics-qc-selftest-") as temporary_name:
        root = Path(temporary_name)
        regular = root / "features.tsv"
        regular.write_text(feature_text, encoding="utf-8")
        payload, text = read_local_file(regular, "feature-table", root=root)
        check(payload == feature_text.encode() and text == feature_text,
              "regular input read differs")
        linked_input = root / "linked.tsv"
        linked_input.symlink_to(regular)
        expect_issue("input-not-regular-file",
                     lambda: read_local_file(linked_input, "feature-table", root=root))

        expect_issue("parent-traversal", lambda: read_local_file(
            Path("..") / "outside.tsv", "feature-table", root=root))
        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "inside.tsv").write_text(feature_text, encoding="utf-8")
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect_issue("input-parent-symlink", lambda: read_local_file(
            linked_input_parent / "inside.tsv", "feature-table", root=root))

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

        symlink_root = root / "root-link"
        symlink_root.symlink_to(real_parent, target_is_directory=True)
        try:
            write_new(Path("report.json"), "{}\n", root=symlink_root)
        except PermissionError:
            checks += 1
        else:
            raise AssertionError("symlinked output root was accepted")

        fsync_output = root / "post-link-fsync.json"
        real_fsync = os.fsync
        failed_directory_fsync = False

        def fail_first_directory_fsync(descriptor: int) -> None:
            nonlocal failed_directory_fsync
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed_directory_fsync:
                failed_directory_fsync = True
                raise OSError("injected post-link directory fsync failure")
            real_fsync(descriptor)

        os.fsync = fail_first_directory_fsync
        try:
            try:
                write_new(fsync_output, "{}\n", root=root)
            except OSError as exc:
                if "directory fsync failure" not in str(exc):
                    raise
            else:
                raise AssertionError("post-link directory fsync failure was hidden")
        finally:
            os.fsync = real_fsync
        check(failed_directory_fsync and not fsync_output.exists(),
              "post-link directory fsync failure was not rolled back")
        check(not list(root.glob(f".{fsync_output.name}.tmp-*")),
              "post-link directory fsync rollback left a staged file")

        cleanup_output = root / "cleanup-failure.json"
        real_unlink = os.unlink

        def fail_staged_unlink(path: str | bytes, *args: Any, **kwargs: Any) -> None:
            if os.fspath(path).startswith(f".{cleanup_output.name}.tmp-"):
                raise PermissionError("injected staged cleanup failure")
            real_unlink(path, *args, **kwargs)

        os.unlink = fail_staged_unlink
        try:
            try:
                write_new(cleanup_output, "{}\n", root=root)
            except OSError as exc:
                if "publication-rollback-failed" not in str(exc):
                    raise
            else:
                raise AssertionError("post-link cleanup failure was hidden")
        finally:
            os.unlink = real_unlink
        check(not cleanup_output.exists(), "cleanup failure left the final output")
        staged_leftovers = list(root.glob(f".{cleanup_output.name}.tmp-*"))
        check(len(staged_leftovers) == 1,
              "cleanup failure did not expose its staged file")
        staged_leftovers[0].unlink()

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION},
                     sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--feature-table", type=Path)
    result.add_argument("--metadata", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--intensity-semantics", choices=INTENSITY_SEMANTICS)
    result.add_argument("--missing-token")
    result.add_argument("--zero-semantics", choices=ZERO_SEMANTICS)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    required = ("feature_table", "metadata", "output", "intensity_semantics",
                "missing_token", "zero_semantics")
    missing = [name for name in required if getattr(arguments, name) is None]
    if missing:
        parser().error("required for execution: " + ", ".join(
            f"--{name.replace('_', '-')}" for name in missing))
    try:
        feature_payload, feature_text = read_local_file(arguments.feature_table,
                                                        "feature-table")
        metadata_payload, metadata_text = read_local_file(arguments.metadata, "metadata")
        report = analyze(
            feature_payload, feature_text, metadata_payload, metadata_text,
            intensity_semantics=arguments.intensity_semantics,
            missing_token=arguments.missing_token,
            zero_semantics=arguments.zero_semantics,
        )
        rendered = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
        write_new(arguments.output, rendered)
        print(json.dumps({"analysis_performed": True,
                          "features": report["feature_qc"]["feature_count"],
                          "output": str(arguments.output),
                          "samples": report["joins"]["matched_sample_count"],
                          "status": "completed"}, sort_keys=True))
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
