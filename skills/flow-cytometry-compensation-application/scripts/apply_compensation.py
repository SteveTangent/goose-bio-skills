#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply one declared spillover matrix to an extracted event TSV."""

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
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

VERSION = "0.8.0"
MAX_BYTES = 16 * 1024 * 1024
MAX_CHANNELS = 32
MAX_EVENTS = 100_000
PIVOT_EPSILON = 1e-12
RESIDUAL_LIMIT = 1e-8
CONDITION_LIMIT = 1e8
OFF_DIAGONAL_ABS_LIMIT = 1.0
MAX_NUMBER_CHARS = 128
MAX_IDENTIFIER_CHARS = 128
RESERVED_CHANNEL_IDS = frozenset({"event_id", "source_channel"})
DECIMAL_NUMBER = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z"
)


class ContractError(Exception):
    def __init__(self, code: str, message: str, status: str = "invalid-input") -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class OutputTarget:
    path: Path
    directory_fd: int
    name: str
    directory_identity: tuple[int, int]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_parent_no_symlinks(path_text: str | Path, role: str) -> tuple[Path, int, str]:
    raw = os.fspath(path_text)
    status = "invalid-output" if role == "output" else "invalid-input"
    if not raw or "\x00" in raw:
        raise ContractError(
            f"invalid-{role}-path", f"{role} path is empty or invalid", status
        )
    supplied = Path(raw)
    if ".." in supplied.parts:
        raise ContractError(
            f"invalid-{role}-path",
            f"{role} path must not contain parent traversal",
            status,
        )
    if supplied.name in {"", ".", ".."}:
        raise ContractError(
            f"invalid-{role}-path", f"{role} path must name a file", status
        )

    if supplied.is_absolute():
        anchor = Path(supplied.anchor)
        parts = supplied.parts[1:]
    else:
        anchor = Path.cwd()
        parts = supplied.parts
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(anchor, flags)
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return supplied, descriptor, parts[-1]
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ContractError(
            f"unsafe-{role}-parent",
            f"{role} parent must exist and contain no symlink components",
            status,
        ) from exc


def read_stable(path_text: str) -> tuple[bytes, dict[str, Any]]:
    path, directory_fd, name = open_parent_no_symlinks(path_text, "input")
    fd = -1
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            before_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(before_path.st_mode):
                raise ContractError("input-symlink", "input path must not contain symlinks")
            fd = os.open(name, flags, dir_fd=directory_fd)
        except ContractError:
            raise
        except OSError as exc:
            raise ContractError("input-unavailable", f"cannot open input: {exc.strerror}") from exc
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("input-not-regular", "input must resolve to a regular file")
        if (before.st_dev, before.st_ino) != (before_path.st_dev, before_path.st_ino):
            raise ContractError("input-changed", "input changed before it was read")
        if before.st_size > MAX_BYTES:
            raise ContractError("input-too-large", f"input exceeds {MAX_BYTES} bytes")
        chunks: list[bytes] = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        try:
            after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise ContractError("input-changed", "input changed while being read") from exc
        if len(data) > MAX_BYTES:
            raise ContractError("input-too-large", f"input exceeds {MAX_BYTES} bytes")
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        identity_path = (
            after_path.st_dev,
            after_path.st_ino,
            after_path.st_size,
            after_path.st_mtime_ns,
            after_path.st_ctime_ns,
        )
        if identity_before != identity_after or identity_after != identity_path or len(data) != before.st_size:
            raise ContractError("input-changed", "input changed while being read")
        return data, {"sha256": sha256(data), "size_bytes": len(data)}
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(directory_fd)


def decode_tsv(data: bytes, label: str) -> list[list[str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid-utf8", f"{label} must be UTF-8") from exc
    if "\x00" in text:
        raise ContractError("invalid-character", f"{label} contains a NUL byte")
    try:
        rows = list(
            csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        )
    except csv.Error as exc:
        raise ContractError("invalid-tsv", f"{label} is not valid TSV: {exc}") from exc
    if any("\r" in field or "\n" in field for row in rows for field in row):
        raise ContractError(
            "invalid-character", f"{label} contains a line break inside a field"
        )
    if not rows or not rows[0]:
        raise ContractError("empty-table", f"{label} is empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ContractError("ragged-table", f"{label} has inconsistent columns")
    return rows


def valid_identifier(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= MAX_IDENTIFIER_CHARS
        and all(32 < ord(ch) < 127 for ch in value)
    )


def parse_decimal(token: str, label: str) -> Decimal:
    if (
        not token
        or len(token) > MAX_NUMBER_CHARS
        or DECIMAL_NUMBER.fullmatch(token) is None
    ):
        raise ContractError("invalid-number", f"{label} must use strict decimal syntax")
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ContractError("invalid-number", f"{label} is not numeric") from exc
    if not value.is_finite():
        raise ContractError("nonfinite-number", f"{label} must be finite")
    return value


def decimal_to_float(value: Decimal, label: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ContractError("nonfinite-number", f"{label} exceeds finite float range")
    if value != 0 and converted == 0:
        raise ContractError("numeric-underflow", f"{label} is nonzero but underflows float range")
    return converted


def parse_number(token: str, label: str) -> float:
    return decimal_to_float(parse_decimal(token, label), label)


def parse_events(rows: list[list[str]]) -> tuple[list[str], list[str], list[list[float]]]:
    header = rows[0]
    if len(header) < 2 or header[0] != "event_id":
        raise ContractError("event-header", "event table must start with event_id")
    channels = header[1:]
    if (
        len(channels) > MAX_CHANNELS
        or len(set(channels)) != len(channels)
        or any(channel in RESERVED_CHANNEL_IDS for channel in channels)
        or not all(valid_identifier(v) for v in channels)
    ):
        raise ContractError("invalid-channels", "event channels must be unique bounded ASCII identifiers")
    if len(rows) - 1 > MAX_EVENTS:
        raise ContractError("too-many-events", f"event table exceeds {MAX_EVENTS} rows")
    event_ids: list[str] = []
    seen_event_ids: set[str] = set()
    values: list[list[float]] = []
    for row_index, row in enumerate(rows[1:], 2):
        event_id = row[0]
        if not valid_identifier(event_id) or event_id in seen_event_ids:
            raise ContractError("invalid-event-id", f"row {row_index} has an invalid or duplicate event_id")
        event_ids.append(event_id)
        seen_event_ids.add(event_id)
        values.append([parse_number(token, f"event row {row_index}") for token in row[1:]])
    if not event_ids:
        raise ContractError("empty-events", "event table must contain at least one event")
    return channels, event_ids, values


def parse_matrix(rows: list[list[str]], channels: list[str]) -> list[list[float]]:
    if rows[0][0] != "source_channel" or rows[0][1:] != channels:
        raise ContractError("matrix-header-mismatch", "spillover headers must exactly match event channels")
    if len(rows) - 1 != len(channels):
        raise ContractError("matrix-not-square", "spillover matrix must have one row per channel")
    labels = [row[0] for row in rows[1:]]
    if labels != channels:
        raise ContractError("matrix-row-mismatch", "spillover row labels must exactly match channel order")
    decimal_matrix = [
        [parse_decimal(token, f"spillover row {index}") for token in row[1:]]
        for index, row in enumerate(rows[1:], 2)
    ]
    for row_index, row in enumerate(decimal_matrix):
        for column_index, value in enumerate(row):
            if row_index == column_index:
                if value != Decimal(1):
                    raise ContractError(
                        "nonunit-spillover-diagonal",
                        "spillover matrix diagonal entries must be exactly 1",
                        "needs-decision",
                    )
            elif abs(value) > Decimal(1):
                raise ContractError(
                    "spillover-coefficient-out-of-range",
                    f"off-diagonal spillover coefficients must have absolute value at most {OFF_DIAGONAL_ABS_LIMIT}",
                    "needs-decision",
                )
    return [
        [decimal_to_float(value, f"spillover row {index}") for value in row]
        for index, row in enumerate(decimal_matrix, 2)
    ]


def invert(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for column in range(n):
        pivot_row = max(range(column, n), key=lambda r: abs(augmented[r][column]))
        pivot = augmented[pivot_row][column]
        if not math.isfinite(pivot) or abs(pivot) <= PIVOT_EPSILON:
            raise ContractError("singular-matrix", "spillover matrix is singular or numerically unstable", "needs-decision")
        augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        augmented[column] = [value / pivot for value in augmented[column]]
        if not all(math.isfinite(value) for value in augmented[column]):
            raise ContractError("matrix-overflow", "matrix inversion exceeded finite numeric range", "needs-decision")
        for row_index in range(n):
            if row_index == column:
                continue
            factor = augmented[row_index][column]
            augmented[row_index] = [a - factor * b for a, b in zip(augmented[row_index], augmented[column])]
            if not all(math.isfinite(value) for value in augmented[row_index]):
                raise ContractError("matrix-overflow", "matrix inversion exceeded finite numeric range", "needs-decision")
    return [row[n:] for row in augmented]


def multiply_row(row: list[float], matrix: list[list[float]]) -> list[float]:
    output: list[float] = []
    for column in range(len(matrix)):
        try:
            value = math.fsum(row[index] * matrix[index][column] for index in range(len(row)))
        except (OverflowError, ValueError) as exc:
            raise ContractError("numeric-overflow", "compensation exceeded finite numeric range", "needs-decision") from exc
        if not math.isfinite(value):
            raise ContractError("numeric-overflow", "compensation exceeded finite numeric range", "needs-decision")
        output.append(0.0 if value == 0.0 else value)
    return output


def infinity_norm(matrix: list[list[float]]) -> float:
    try:
        result = max(math.fsum(abs(value) for value in row) for row in matrix)
    except (OverflowError, ValueError) as exc:
        raise ContractError(
            "unstable-matrix",
            "spillover condition calculation exceeded finite numeric range",
            "needs-decision",
        ) from exc
    if not math.isfinite(result):
        raise ContractError(
            "unstable-matrix",
            "spillover condition calculation exceeded finite numeric range",
            "needs-decision",
        )
    return result


def condition_number_infinity(matrix: list[list[float]], inverse: list[list[float]]) -> float:
    condition = infinity_norm(matrix) * infinity_norm(inverse)
    if not math.isfinite(condition) or condition > CONDITION_LIMIT:
        raise ContractError(
            "ill-conditioned-matrix",
            f"spillover infinity-norm condition number exceeds {CONDITION_LIMIT:g}",
            "needs-decision",
        )
    return condition


def inverse_residual(matrix: list[list[float]], inverse: list[list[float]]) -> float:
    residual = 0.0
    n = len(matrix)
    for row in range(n):
        for column in range(n):
            try:
                value = math.fsum(
                    matrix[row][k] * inverse[k][column] for k in range(n)
                )
            except (OverflowError, ValueError) as exc:
                raise ContractError(
                    "unstable-matrix",
                    "spillover inverse residual exceeded finite numeric range",
                    "needs-decision",
                ) from exc
            if not math.isfinite(value):
                raise ContractError(
                    "unstable-matrix",
                    "spillover inverse residual exceeded finite numeric range",
                    "needs-decision",
                )
            residual = max(residual, abs(value - (1.0 if row == column else 0.0)))
    if not math.isfinite(residual) or residual > RESIDUAL_LIMIT:
        raise ContractError("unstable-matrix", "spillover inverse failed the residual check", "needs-decision")
    return residual


def format_number(value: float) -> str:
    return "0" if value == 0.0 else repr(value)


def event_tsv(channels: list[str], event_ids: list[str], values: list[list[float]]) -> bytes:
    lines = ["\t".join(["event_id", *channels])]
    lines.extend("\t".join([event_id, *(format_number(v) for v in row)]) for event_id, row in zip(event_ids, values))
    return ("\n".join(lines) + "\n").encode()


def output_target(path_text: str | Path) -> OutputTarget:
    path, directory_fd, name = open_parent_no_symlinks(path_text, "output")
    try:
        directory_state = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_state.st_mode):
            raise ContractError(
                "output-parent-not-directory",
                "output parent must be a directory",
                "invalid-output",
            )
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ContractError("output-exists", "output already exists", "invalid-output")
        return OutputTarget(
            path=path,
            directory_fd=directory_fd,
            name=name,
            directory_identity=(directory_state.st_dev, directory_state.st_ino),
        )
    except BaseException:
        os.close(directory_fd)
        raise


def write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short write made no progress")
        offset += written


def unlink_owned(name: str, target: OutputTarget, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=target.directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=target.directory_fd)
    return True


def publish_pair(first_path: Path, first_data: bytes, second_path: Path, second_data: bytes) -> None:
    first = output_target(first_path)
    try:
        second = output_target(second_path)
    except BaseException:
        os.close(first.directory_fd)
        raise
    targets = [first, second]
    datas = [first_data, second_data]
    temporary: list[tuple[OutputTarget, str, tuple[int, int]]] = []
    published: list[tuple[OutputTarget, tuple[int, int]]] = []
    original_error: BaseException | None = None
    cleanup_failures: list[str] = []
    try:
        if (
            first.directory_identity == second.directory_identity
            and first.name == second.name
        ):
            raise ContractError(
                "output-collision", "output paths must be distinct", "invalid-output"
            )
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for target, data in zip(targets, datas):
            temp_name = f".{target.name}.tmp-{secrets.token_hex(12)}"
            descriptor = -1
            try:
                descriptor = os.open(
                    temp_name, flags, 0o600, dir_fd=target.directory_fd
                )
                state = os.fstat(descriptor)
                identity = (state.st_dev, state.st_ino)
                temporary.append((target, temp_name, identity))
                write_all(descriptor, data)
                os.fsync(descriptor)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

        for target, temp_name, identity in temporary:
            try:
                os.link(
                    temp_name,
                    target.name,
                    src_dir_fd=target.directory_fd,
                    dst_dir_fd=target.directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ContractError(
                    "output-exists",
                    "output appeared before publication",
                    "invalid-output",
                ) from exc
            published.append((target, identity))
            published_state = os.stat(
                target.name, dir_fd=target.directory_fd, follow_symlinks=False
            )
            if (published_state.st_dev, published_state.st_ino) != identity:
                raise OSError("published output identity differs from staged data")

        for target in targets:
            os.fsync(target.directory_fd)
        for target, temp_name, identity in temporary:
            if not unlink_owned(temp_name, target, identity):
                raise OSError("staged output identity changed before cleanup")
        temporary.clear()
        for target in targets:
            os.fsync(target.directory_fd)
        for target, identity in published:
            final_state = os.stat(
                target.name, dir_fd=target.directory_fd, follow_symlinks=False
            )
            if (final_state.st_dev, final_state.st_ino) != identity:
                raise OSError("published output identity changed before completion")
        return
    except BaseException as exc:
        original_error = exc
    finally:
        if original_error is not None:
            for target, identity in reversed(published):
                try:
                    if not unlink_owned(target.name, target, identity):
                        cleanup_failures.append(f"published:{target.name}:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"published:{target.name}:{exc.__class__.__name__}")
            for target, temp_name, identity in reversed(temporary):
                try:
                    if not unlink_owned(temp_name, target, identity):
                        cleanup_failures.append(f"staged:{temp_name}:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"staged:{temp_name}:{exc.__class__.__name__}")
            for target in targets:
                try:
                    os.fsync(target.directory_fd)
                except OSError as exc:
                    cleanup_failures.append(f"directory:{target.name}:{exc.__class__.__name__}")
        for target in targets:
            os.close(target.directory_fd)

    if cleanup_failures:
        raise ContractError(
            "publication-rollback-failed",
            "two-output publication failed and owned files could not all be rolled back: "
            + ", ".join(cleanup_failures),
            "io-error",
        ) from original_error
    if original_error is not None:
        raise original_error


def execute(events_path: str, spillover_path: str, output_events: str, output_report: str) -> dict[str, Any]:
    events_bytes, events_binding = read_stable(events_path)
    matrix_bytes, matrix_binding = read_stable(spillover_path)
    channels, event_ids, observed = parse_events(decode_tsv(events_bytes, "event table"))
    matrix = parse_matrix(decode_tsv(matrix_bytes, "spillover table"), channels)
    inverse = invert(matrix)
    condition = condition_number_infinity(matrix, inverse)
    residual = inverse_residual(matrix, inverse)
    compensated = [multiply_row(row, inverse) for row in observed]
    output_bytes = event_tsv(channels, event_ids, compensated)
    report = {
        "schema_version": "0.1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": "flow-cytometry-compensation-application",
        "tool_version": VERSION,
        "inputs": {
            "events": events_binding,
            "spillover": matrix_binding,
        },
        "dimensions": {"channel_count": len(channels), "event_count": len(event_ids)},
        "channels": channels,
        "matrix_contract": {
            "equation": "observed-row-vector=true-row-vector-times-spillover",
            "condition_limit_infinity_norm": CONDITION_LIMIT,
            "condition_number_infinity_norm": condition,
            "inverse_residual_max_abs": residual,
            "off_diagonal_absolute_limit": OFF_DIAGONAL_ABS_LIMIT,
            "pivot_epsilon": PIVOT_EPSILON,
            "residual_limit": RESIDUAL_LIMIT,
            "unit_diagonal_required": True,
        },
        "numeric_contract": {
            "accepted_input_syntax": "strict-finite-decimal-with-optional-exponent",
            "maximum_number_characters": MAX_NUMBER_CHARS,
            "output_float_format": "python-shortest-round-trip-representation",
        },
        "outputs": {
            "events": {"filename": Path(output_events).name, "sha256": sha256(output_bytes), "size_bytes": len(output_bytes)},
            "report": {"filename": Path(output_report).name},
        },
        "limitations": [
            "The supplied matrix was applied but not estimated, selected, or scientifically validated.",
            "Negative compensated values are preserved without transformation or interpretation.",
            "FCS parsing, transformations, gating, labeling, QC decisions, and clinical interpretation were not performed.",
        ],
    }
    report_bytes = canonical_json(report)
    publish_pair(Path(output_events), output_bytes, Path(output_report), report_bytes)
    return {"status": "completed", "analysis_performed": True, "events": len(event_ids), "channels": len(channels), "outputs_created": 2}


def self_test() -> dict[str, Any]:
    checks = 0

    def expect(code: str, action: Any, status: str | None = None) -> None:
        nonlocal checks
        try:
            action()
        except ContractError as exc:
            assert exc.code == code, (code, exc.code)
            if status is not None:
                assert exc.status == status, (status, exc.status)
        else:
            raise AssertionError(f"{code} boundary was accepted")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="bio02-flow-comp-") as temp:
        root = Path(temp).resolve()
        events = root / "events.tsv"
        spill = root / "spill.tsv"
        events.write_text("event_id\tFITC-A\tPE-A\tAPC-A\ne1\t105\t58\t25\ne2\t210\t116\t50\ne3\t0\t0\t0\ne4\t55\t107\t210\ne5\t10.5\t5.8\t2.5\n")
        spill.write_text("source_channel\tFITC-A\tPE-A\tAPC-A\nFITC-A\t1\t0.1\t0\nPE-A\t0.05\t1\t0.02\nAPC-A\t0\t0.03\t1\n")
        one = root / "one.tsv"
        one_report = root / "one.json"
        result = execute(str(events), str(spill), str(one), str(one_report))
        assert result["status"] == "completed" and result["events"] == 5
        checks += 1
        first_bytes = one.read_bytes()
        first_report = one_report.read_bytes()
        two = root / "two.tsv"
        two_report = root / "two.json"
        execute(str(events), str(spill), str(two), str(two_report))
        assert first_bytes == two.read_bytes()
        checks += 1
        report_one = json.loads(first_report)
        report_two = json.loads(two_report.read_bytes())
        assert (
            report_one["matrix_contract"]["unit_diagonal_required"] is True
            and report_one["matrix_contract"]["condition_number_infinity_norm"]
            <= CONDITION_LIMIT
            and report_one["numeric_contract"]["maximum_number_characters"]
            == MAX_NUMBER_CHARS
        )
        checks += 1
        report_one["outputs"]["events"]["filename"] = "normalized.tsv"
        report_one["outputs"]["report"]["filename"] = "normalized.json"
        report_two["outputs"]["events"]["filename"] = "normalized.tsv"
        report_two["outputs"]["report"]["filename"] = "normalized.json"
        assert report_one == report_two
        checks += 1
        rows = decode_tsv(first_bytes, "output")
        assert rows[0] == ["event_id", "FITC-A", "PE-A", "APC-A"] and len(rows) == 6
        checks += 1
        assert all(abs(float(value) - expected) < 1e-9 for value, expected in zip(rows[1][1:], [102.64933628318583, 47.01327433628318, 24.059734513274336]))
        checks += 1
        assert all(
            value == "0" or repr(float(value)) == value
            for row in rows[1:]
            for value in row[1:]
        )
        checks += 1
        try:
            execute(str(events), str(spill), str(one), str(root / "new.json"))
            raise AssertionError("overwrite accepted")
        except ContractError as exc:
            assert exc.code == "output-exists"
        checks += 1
        bad = root / "bad.tsv"
        bad.write_text("source_channel\tFITC-A\tPE-A\tAPC-A\nFITC-A\t1\t1\t0\nPE-A\t1\t1\t0\nAPC-A\t0\t0\t1\n")
        try:
            execute(str(events), str(bad), str(root / "bad-out.tsv"), str(root / "bad-out.json"))
            raise AssertionError("singular matrix accepted")
        except ContractError as exc:
            assert exc.code == "singular-matrix" and exc.status == "needs-decision"
        checks += 1
        mismatch = root / "mismatch.tsv"
        mismatch.write_text("source_channel\tPE-A\tFITC-A\tAPC-A\nFITC-A\t1\t0\t0\nPE-A\t0\t1\t0\nAPC-A\t0\t0\t1\n")
        try:
            execute(str(events), str(mismatch), str(root / "m.tsv"), str(root / "m.json"))
            raise AssertionError("mismatch accepted")
        except ContractError as exc:
            assert exc.code == "matrix-header-mismatch"
        checks += 1
        nonfinite = root / "nonfinite.tsv"
        nonfinite.write_text("event_id\tFITC-A\tPE-A\tAPC-A\ne1\tnan\t1\t1\n")
        try:
            execute(str(nonfinite), str(spill), str(root / "n.tsv"), str(root / "n.json"))
            raise AssertionError("nonfinite accepted")
        except ContractError as exc:
            assert exc.code == "invalid-number"
        checks += 1
        link = root / "events-link.tsv"
        link.symlink_to(events)
        try:
            read_stable(str(link))
            raise AssertionError("leaf symlink accepted")
        except ContractError as exc:
            assert exc.code == "input-symlink"
        checks += 1

        for invalid_token in (" 1", "1 ", "1_0"):
            expect(
                "invalid-number",
                lambda token=invalid_token: parse_number(token, "probe"),
            )

        float_overflow = decode_tsv(
            b"event_id\tFITC-A\ne1\t1e999\n", "float-overflow-event"
        )
        expect("nonfinite-number", lambda: parse_events(float_overflow))

        float_underflow = decode_tsv(
            b"event_id\tFITC-A\ne1\t1e-999\n", "float-underflow-event"
        )
        expect("numeric-underflow", lambda: parse_events(float_underflow))

        for embedded_line_break in (b'"e\n1"\t1\n', b'"e\r1"\t1\r\n'):
            expect(
                "invalid-character",
                lambda payload=embedded_line_break: decode_tsv(
                    b"event_id\tFITC-A\n" + payload,
                    "embedded-line-break",
                ),
            )

        reserved = decode_tsv(
            b"event_id\tevent_id\ne1\t1\n", "reserved-channel"
        )
        expect("invalid-channels", lambda: parse_events(reserved))

        whitespace_channel = decode_tsv(
            b"event_id\tFITC A\ne1\t1\n", "whitespace-channel"
        )
        expect("invalid-channels", lambda: parse_events(whitespace_channel))

        duplicate_ids = decode_tsv(
            b"event_id\tFITC-A\ne1\t1\ne1\t2\n", "duplicate-event"
        )
        expect("invalid-event-id", lambda: parse_events(duplicate_ids))

        nonunit_rows = decode_tsv(
            b"source_channel\tFITC-A\tPE-A\nFITC-A\t2\t0.1\nPE-A\t0.1\t1\n",
            "nonunit-matrix",
        )
        expect(
            "nonunit-spillover-diagonal",
            lambda: parse_matrix(nonunit_rows, ["FITC-A", "PE-A"]),
            "needs-decision",
        )
        rounded_nonunit_rows = decode_tsv(
            b"source_channel\tFITC-A\tPE-A\n"
            b"FITC-A\t1.0000000000000001\t0.1\nPE-A\t0.1\t1\n",
            "rounded-nonunit-matrix",
        )
        expect(
            "nonunit-spillover-diagonal",
            lambda: parse_matrix(rounded_nonunit_rows, ["FITC-A", "PE-A"]),
            "needs-decision",
        )
        oversized_rows = decode_tsv(
            b"source_channel\tFITC-A\tPE-A\nFITC-A\t1\t1.1\nPE-A\t0.1\t1\n",
            "oversized-matrix",
        )
        expect(
            "spillover-coefficient-out-of-range",
            lambda: parse_matrix(oversized_rows, ["FITC-A", "PE-A"]),
            "needs-decision",
        )
        rounded_oversized_rows = decode_tsv(
            b"source_channel\tFITC-A\tPE-A\n"
            b"FITC-A\t1\t1.0000000000000001\nPE-A\t0.1\t1\n",
            "rounded-oversized-matrix",
        )
        expect(
            "spillover-coefficient-out-of-range",
            lambda: parse_matrix(rounded_oversized_rows, ["FITC-A", "PE-A"]),
            "needs-decision",
        )
        near_collinear = [[1.0, 0.99999999999], [0.99999999999, 1.0]]
        near_inverse = invert(near_collinear)
        expect(
            "ill-conditioned-matrix",
            lambda: condition_number_infinity(near_collinear, near_inverse),
            "needs-decision",
        )
        expect(
            "unstable-matrix",
            lambda: inverse_residual(
                [[1e308, 1e308], [1.0, 1.0]],
                [[1e308, 1.0], [-1e308, -1.0]],
            ),
            "needs-decision",
        )

        fifo = root / "events.fifo"
        os.mkfifo(fifo)
        expect("input-not-regular", lambda: read_stable(str(fifo)))

        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "events.tsv").write_bytes(events.read_bytes())
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect(
            "unsafe-input-parent",
            lambda: read_stable(str(linked_input_parent / "events.tsv")),
        )

        short_one = root / "short-one.bin"
        short_two = root / "short-two.bin"
        first_payload = b"abcdefghij" * 17
        second_payload = b"0123456789" * 19
        original_write = os.write

        def short_write(descriptor: int, data: bytes) -> int:
            return original_write(descriptor, data[:5])

        os.write = short_write
        try:
            publish_pair(short_one, first_payload, short_two, second_payload)
        finally:
            os.write = original_write
        assert short_one.read_bytes() == first_payload and short_two.read_bytes() == second_payload
        checks += 1

        rollback_one = root / "rollback-one.bin"
        rollback_two = root / "rollback-two.bin"
        original_link = os.link
        link_calls = 0

        def fail_second_link(*args: Any, **kwargs: Any) -> None:
            nonlocal link_calls
            link_calls += 1
            if link_calls == 2:
                raise FileExistsError("injected second publication collision")
            original_link(*args, **kwargs)

        os.link = fail_second_link
        try:
            expect(
                "output-exists",
                lambda: publish_pair(rollback_one, b"one", rollback_two, b"two"),
                "invalid-output",
            )
        finally:
            os.link = original_link
        assert not rollback_one.exists() and not rollback_two.exists()
        checks += 1

        postlink_one = root / "postlink-one.bin"
        postlink_two = root / "postlink-two.bin"
        original_stat = os.stat
        injected_stat_failure = False

        def fail_first_postlink_stat(path: str | bytes, *args: Any, **kwargs: Any) -> os.stat_result:
            nonlocal injected_stat_failure
            result = original_stat(path, *args, **kwargs)
            if (
                os.fspath(path) == postlink_one.name
                and kwargs.get("dir_fd") is not None
                and not injected_stat_failure
            ):
                injected_stat_failure = True
                raise OSError("injected post-link verification failure")
            return result

        os.stat = fail_first_postlink_stat
        try:
            try:
                publish_pair(postlink_one, b"one", postlink_two, b"two")
            except OSError:
                pass
            else:
                raise AssertionError("post-link verification failure was ignored")
        finally:
            os.stat = original_stat
        assert injected_stat_failure and not postlink_one.exists() and not postlink_two.exists()
        checks += 1

        detected_one = root / "detected-one.bin"
        detected_two = root / "detected-two.bin"
        original_unlink = os.unlink
        link_calls = 0

        def fail_published_unlink(path: str | bytes, *args: Any, **kwargs: Any) -> None:
            if os.fspath(path) == detected_one.name:
                raise PermissionError("injected rollback failure")
            original_unlink(path, *args, **kwargs)

        os.link = fail_second_link
        os.unlink = fail_published_unlink
        try:
            expect(
                "publication-rollback-failed",
                lambda: publish_pair(detected_one, b"one", detected_two, b"two"),
                "io-error",
            )
        finally:
            os.link = original_link
            os.unlink = original_unlink
        assert detected_one.read_bytes() == b"one" and not detected_two.exists()
        detected_one.unlink()
        checks += 1

        real_output_parent = root / "real-output-parent"
        real_output_parent.mkdir()
        linked_output_parent = root / "linked-output-parent"
        linked_output_parent.symlink_to(real_output_parent, target_is_directory=True)
        expect(
            "unsafe-output-parent",
            lambda: publish_pair(
                linked_output_parent / "a.tsv",
                b"a",
                root / "safe-report.json",
                b"b",
            ),
            "invalid-output",
        )

        expect(
            "output-collision",
            lambda: publish_pair(
                root / "same-output.bin",
                b"one",
                root / "same-output.bin",
                b"two",
            ),
            "invalid-output",
        )
        assert not any(path.name.startswith(".") and path.name not in {".", ".."} for path in root.iterdir())
        checks += 1
    return {"checks": checks, "status": "pass", "version": VERSION}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--events")
    result.add_argument("--spillover")
    result.add_argument("--output-events")
    result.add_argument("--output-report")
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.version:
        print(VERSION)
        return 0
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True))
        return 0
    missing = [name for name in ("events", "spillover", "output_events", "output_report") if getattr(args, name) is None]
    if missing:
        print(json.dumps({"status": "invalid-input", "analysis_performed": False, "code": "missing-argument", "missing": missing}, sort_keys=True), file=sys.stderr)
        return 2
    try:
        print(json.dumps(execute(args.events, args.spillover, args.output_events, args.output_report), sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({"status": exc.status, "analysis_performed": False, "code": exc.code, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3 if exc.status in {"needs-tool", "io-error"} else 2
    except OSError as exc:
        print(json.dumps({"status": "io-error", "analysis_performed": False, "code": "io-error", "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
