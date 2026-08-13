#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply declared per-channel arcsinh cofactors to an extracted event TSV."""

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
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    Decimal,
    DecimalException,
    InvalidOperation,
    Underflow,
    localcontext,
)
from pathlib import Path
from typing import Any

VERSION = "0.8.0"
MAX_BYTES = 16 * 1024 * 1024
MAX_CHANNELS = 64
MAX_EVENTS = 100_000
MAX_IDENTIFIER_CHARS = 128
MAX_NUMBER_CHARS = 128
DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
RESERVED_CHANNELS = {"event_id", "channel"}


class ContractError(ValueError):
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
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_parent_no_symlinks(path_text: str | Path, role: str) -> tuple[Path, int, str]:
    raw = os.fspath(path_text)
    status = "invalid-output" if role == "output" else "invalid-input"
    if not raw or "\x00" in raw:
        raise ContractError(f"invalid-{role}-path", f"{role} path is empty or invalid", status)
    supplied = Path(raw)
    if ".." in supplied.parts:
        raise ContractError(
            f"invalid-{role}-path", f"{role} path must not contain parent traversal", status
        )
    if supplied.name in {"", ".", ".."}:
        raise ContractError(f"invalid-{role}-path", f"{role} path must name a file", status)

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
    _path, directory_fd, name = open_parent_no_symlinks(path_text, "input")
    descriptor = -1
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
            descriptor = os.open(name, flags, dir_fd=directory_fd)
        except ContractError:
            raise
        except OSError as exc:
            raise ContractError("input-unavailable", f"cannot open input: {exc.strerror}") from exc
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("input-not-regular", "input must resolve to a regular file")
        if (before.st_dev, before.st_ino) != (before_path.st_dev, before_path.st_ino):
            raise ContractError("input-changed", "input changed before it was read")
        if before.st_size > MAX_BYTES:
            raise ContractError("input-too-large", f"input exceeds {MAX_BYTES} bytes")
        chunks: list[bytes] = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        try:
            after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise ContractError("input-changed", "input changed while being read") from exc
        if len(data) > MAX_BYTES:
            raise ContractError("input-too-large", f"input exceeds {MAX_BYTES} bytes")
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        path_identity = (
            after_path.st_dev,
            after_path.st_ino,
            after_path.st_size,
            after_path.st_mtime_ns,
            after_path.st_ctime_ns,
        )
        if before_identity != after_identity or after_identity != path_identity or len(data) != before.st_size:
            raise ContractError("input-changed", "input changed while being read")
        return data, {"sha256": sha256(data), "size_bytes": len(data)}
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


def decode_tsv(data: bytes, label: str) -> list[list[str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid-utf8", f"{label} must be UTF-8") from exc
    if "\x00" in text:
        raise ContractError("invalid-character", f"{label} contains a NUL byte")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True))
    except csv.Error as exc:
        raise ContractError("invalid-tsv", f"{label} is not valid TSV: {exc}") from exc
    if any("\r" in field or "\n" in field for row in rows for field in row):
        raise ContractError("invalid-character", f"{label} contains a line break inside a field")
    if not rows or not rows[0]:
        raise ContractError("empty-table", f"{label} is empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ContractError("ragged-table", f"{label} has inconsistent columns")
    return rows


def valid_identifier(value: str) -> bool:
    return bool(value) and len(value) <= MAX_IDENTIFIER_CHARS and all(32 < ord(ch) < 127 for ch in value)


def parse_decimal(token: str, label: str) -> Decimal:
    if not token or len(token) > MAX_NUMBER_CHARS or DECIMAL_RE.fullmatch(token) is None:
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
        raise ContractError("numeric-overflow", f"{label} exceeds finite float range", "needs-tool")
    if value != 0 and converted == 0:
        raise ContractError("numeric-underflow", f"{label} underflows float range", "needs-tool")
    return converted


def parse_events(rows: list[list[str]]) -> tuple[list[str], list[str], list[list[str]], list[list[Decimal]]]:
    header = rows[0]
    if len(header) < 2 or header[0] != "event_id":
        raise ContractError("invalid-events-header", "event table must start with event_id")
    channels = header[1:]
    if len(channels) > MAX_CHANNELS:
        raise ContractError("too-many-channels", f"event table exceeds {MAX_CHANNELS} channels", "needs-tool")
    if len(set(channels)) != len(channels) or any(
        not valid_identifier(channel) or channel in RESERVED_CHANNELS for channel in channels
    ):
        raise ContractError("invalid-channels", "event channels must be unique nonreserved identifiers")
    if len(rows) - 1 > MAX_EVENTS:
        raise ContractError("too-many-events", f"event table exceeds {MAX_EVENTS} events", "needs-tool")
    event_ids: list[str] = []
    seen: set[str] = set()
    tokens: list[list[str]] = []
    decimals: list[list[Decimal]] = []
    for row_number, row in enumerate(rows[1:], 2):
        event_id = row[0]
        if not valid_identifier(event_id) or event_id in seen:
            raise ContractError("invalid-event-id", f"event row {row_number} has an invalid or duplicate event_id")
        seen.add(event_id)
        event_ids.append(event_id)
        row_tokens = row[1:]
        row_decimals = [
            parse_decimal(token, f"event row {row_number} channel {channel}")
            for channel, token in zip(channels, row_tokens)
        ]
        tokens.append(row_tokens)
        decimals.append(row_decimals)
    if not event_ids:
        raise ContractError("empty-events", "event table must contain at least one event")
    return channels, event_ids, tokens, decimals


def parse_cofactors(rows: list[list[str]], channels: list[str]) -> dict[str, tuple[str, Decimal]]:
    if rows[0] != ["channel", "cofactor"]:
        raise ContractError("invalid-cofactor-header", "cofactor table header must be channel and cofactor")
    if len(rows) == 1:
        raise ContractError("empty-cofactors", "at least one explicit channel cofactor is required", "needs-decision")
    if len(rows) - 1 > MAX_CHANNELS:
        raise ContractError("too-many-cofactors", f"cofactor table exceeds {MAX_CHANNELS} rows", "needs-tool")
    result: dict[str, tuple[str, Decimal]] = {}
    channel_set = set(channels)
    for row_number, row in enumerate(rows[1:], 2):
        channel, token = row
        if not valid_identifier(channel) or channel in result:
            raise ContractError("invalid-cofactor-channel", f"cofactor row {row_number} has an invalid or duplicate channel")
        if channel not in channel_set:
            raise ContractError("unknown-cofactor-channel", f"cofactor channel {channel} is not in the event table")
        value = parse_decimal(token, f"cofactor row {row_number}")
        if value <= 0:
            raise ContractError("nonpositive-cofactor", f"cofactor for {channel} must be greater than zero", "needs-decision")
        result[channel] = (token, value)
    return result


def format_number(value: float) -> str:
    return "0" if value == 0.0 else repr(value)


def transform_events(
    channels: list[str],
    tokens: list[list[str]],
    decimals: list[list[Decimal]],
    cofactors: dict[str, tuple[str, Decimal]],
) -> list[list[str]]:
    transformed: list[list[str]] = []
    for row_number, (row_tokens, row_decimals) in enumerate(zip(tokens, decimals), 2):
        output_row: list[str] = []
        for column, (channel, raw, decimal_value) in enumerate(zip(channels, row_tokens, row_decimals), 2):
            if channel not in cofactors:
                output_row.append(raw)
                continue
            try:
                with localcontext() as context:
                    context.prec = MAX_NUMBER_CHARS * 2 + 32
                    context.Emax = MAX_EMAX
                    context.Emin = MIN_EMIN
                    context.traps[Underflow] = True
                    decimal_ratio = decimal_value / cofactors[channel][1]
            except DecimalException as exc:
                raise ContractError(
                    "unsupported-numeric-range",
                    f"event row {row_number} channel {channel} ratio exceeds the supported decimal range",
                    "needs-tool",
                ) from exc
            if decimal_value != 0 and decimal_ratio == 0:
                raise ContractError(
                    "numeric-underflow",
                    f"event row {row_number} channel {channel} ratio underflowed the supported decimal range",
                    "needs-tool",
                )
            ratio = decimal_to_float(
                decimal_ratio, f"event row {row_number} channel {channel} ratio"
            )
            output_row.append(format_number(math.asinh(ratio)))
        transformed.append(output_row)
    return transformed


def event_tsv(channels: list[str], event_ids: list[str], rows: list[list[str]]) -> bytes:
    lines = ["\t".join(["event_id", *channels])]
    lines.extend("\t".join([event_id, *row]) for event_id, row in zip(event_ids, rows))
    return ("\n".join(lines) + "\n").encode()


def output_target(path_text: str | Path) -> OutputTarget:
    path, directory_fd, name = open_parent_no_symlinks(path_text, "output")
    try:
        directory_state = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_state.st_mode):
            raise ContractError("output-parent-not-directory", "output parent must be a directory", "invalid-output")
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ContractError("output-exists", "output already exists", "invalid-output")
        return OutputTarget(path, directory_fd, name, (directory_state.st_dev, directory_state.st_ino))
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
        if first.directory_identity == second.directory_identity and first.name == second.name:
            raise ContractError("output-collision", "output paths must be distinct", "invalid-output")
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
                descriptor = os.open(temp_name, flags, 0o600, dir_fd=target.directory_fd)
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
                raise ContractError("output-exists", "output appeared before publication", "invalid-output") from exc
            published.append((target, identity))
            state = os.stat(target.name, dir_fd=target.directory_fd, follow_symlinks=False)
            if (state.st_dev, state.st_ino) != identity:
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
            state = os.stat(target.name, dir_fd=target.directory_fd, follow_symlinks=False)
            if (state.st_dev, state.st_ino) != identity:
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
            "two-output publication failed and owned files could not all be rolled back: " + ", ".join(cleanup_failures),
            "io-error",
        ) from original_error
    if original_error is not None:
        raise original_error


def execute(events_path: str, cofactor_path: str, output_events: str, output_report: str) -> dict[str, Any]:
    event_bytes, event_binding = read_stable(events_path)
    cofactor_bytes, cofactor_binding = read_stable(cofactor_path)
    channels, event_ids, tokens, decimals = parse_events(decode_tsv(event_bytes, "event table"))
    cofactors = parse_cofactors(decode_tsv(cofactor_bytes, "cofactor table"), channels)
    transformed = transform_events(channels, tokens, decimals, cofactors)
    output_bytes = event_tsv(channels, event_ids, transformed)
    selected = [channel for channel in channels if channel in cofactors]
    report = {
        "schema_version": "0.1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": "flow-cytometry-arcsinh-transformation",
        "tool_version": VERSION,
        "inputs": {"events": event_binding, "cofactors": cofactor_binding},
        "dimensions": {
            "channel_count": len(channels),
            "event_count": len(event_ids),
            "transformed_channel_count": len(selected),
        },
        "transformation": {
            "formula": "asinh(value/cofactor)",
            "selected_channels": [
                {"channel": channel, "cofactor": cofactors[channel][0]} for channel in selected
            ],
            "unselected_tokens_preserved": True,
        },
        "numeric_contract": {
            "accepted_input_syntax": "strict-finite-decimal-with-optional-exponent",
            "maximum_number_characters": MAX_NUMBER_CHARS,
            "output_float_format": "python-shortest-round-trip-representation",
        },
        "outputs": {
            "events": {
                "filename": Path(output_events).name,
                "sha256": sha256(output_bytes),
                "size_bytes": len(output_bytes),
            },
            "report": {"filename": Path(output_report).name},
        },
        "limitations": [
            "Cofactors were applied but not selected, estimated, or scientifically validated.",
            "Unselected numeric cell tokens are preserved exactly; selected values are floating-point outputs.",
            "FCS parsing, compensation, other transformations, gating, labeling, QC decisions, and clinical interpretation were not performed.",
        ],
    }
    report_bytes = canonical_json(report)
    publish_pair(Path(output_events), output_bytes, Path(output_report), report_bytes)
    return {
        "status": "completed",
        "analysis_performed": True,
        "events": len(event_ids),
        "channels": len(channels),
        "transformed_channels": len(selected),
        "outputs_created": 2,
    }


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

    with tempfile.TemporaryDirectory(prefix="bio02-flow-arcsinh-") as temp:
        root = Path(temp).resolve()
        events = root / "events.tsv"
        cofactors = root / "cofactors.tsv"
        events.write_text(
            "event_id\tFITC-A\tPE-A\tAPC-A\n"
            "e1\t5\t-5\t7.00\n"
            "e2\t-0\t10\t8e0\n",
            encoding="utf-8",
        )
        cofactors.write_text("channel\tcofactor\nPE-A\t10\nFITC-A\t5\n", encoding="utf-8")
        one = root / "one.tsv"
        one_report = root / "one.json"
        result = execute(str(events), str(cofactors), str(one), str(one_report))
        assert result == {
            "status": "completed",
            "analysis_performed": True,
            "events": 2,
            "channels": 3,
            "transformed_channels": 2,
            "outputs_created": 2,
        }
        checks += 1
        rows = decode_tsv(one.read_bytes(), "transformed output")
        assert rows[0] == ["event_id", "FITC-A", "PE-A", "APC-A"]
        assert rows[1][1:] == [repr(math.asinh(1.0)), repr(math.asinh(-0.5)), "7.00"]
        assert rows[2][1:] == ["0", repr(math.asinh(1.0)), "8e0"]
        checks += 1
        report = json.loads(one_report.read_bytes())
        assert report["transformation"]["selected_channels"] == [
            {"channel": "FITC-A", "cofactor": "5"},
            {"channel": "PE-A", "cofactor": "10"},
        ]
        assert report["outputs"]["events"]["sha256"] == sha256(one.read_bytes())
        checks += 1
        two = root / "two.tsv"
        two_report = root / "two.json"
        execute(str(events), str(cofactors), str(two), str(two_report))
        assert one.read_bytes() == two.read_bytes()
        normalized_one = json.loads(one_report.read_bytes())
        normalized_two = json.loads(two_report.read_bytes())
        for value in (normalized_one, normalized_two):
            value["outputs"]["events"]["filename"] = "events.tsv"
            value["outputs"]["report"]["filename"] = "report.json"
        assert normalized_one == normalized_two
        checks += 1
        expect(
            "output-exists",
            lambda: execute(str(events), str(cofactors), str(one), str(root / "unused.json")),
            "invalid-output",
        )
        assert one.read_bytes() == two.read_bytes() and not (root / "unused.json").exists()
        checks += 1

        bad_cofactor = root / "bad-cofactor.tsv"
        bad_cofactor.write_text("channel\tcofactor\nFITC-A\t0\n")
        expect(
            "nonpositive-cofactor",
            lambda: execute(str(events), str(bad_cofactor), str(root / "bad.tsv"), str(root / "bad.json")),
            "needs-decision",
        )
        unknown = root / "unknown.tsv"
        unknown.write_text("channel\tcofactor\nUNKNOWN\t5\n")
        expect(
            "unknown-cofactor-channel",
            lambda: execute(str(events), str(unknown), str(root / "unknown-out.tsv"), str(root / "unknown-out.json")),
        )
        duplicate = root / "duplicate.tsv"
        duplicate.write_text("channel\tcofactor\nFITC-A\t5\nFITC-A\t6\n")
        expect(
            "invalid-cofactor-channel",
            lambda: execute(str(events), str(duplicate), str(root / "dup.tsv"), str(root / "dup.json")),
        )
        empty = root / "empty.tsv"
        empty.write_text("channel\tcofactor\n")
        expect(
            "empty-cofactors",
            lambda: execute(str(events), str(empty), str(root / "empty-out.tsv"), str(root / "empty-out.json")),
            "needs-decision",
        )
        for token in (" 1", "1 ", "1_0", "NaN"):
            expect("invalid-number", lambda value=token: parse_decimal(value, "probe"))
        expect(
            "numeric-overflow",
            lambda: decimal_to_float(parse_decimal("1e999", "probe"), "probe"),
            "needs-tool",
        )
        expect(
            "numeric-underflow",
            lambda: decimal_to_float(parse_decimal("1e-999", "probe"), "probe"),
            "needs-tool",
        )
        exact_extreme_channels = ["A"]
        exact_extreme_cofactor = {"A": ("1e999", Decimal("1e999"))}
        assert transform_events(
            exact_extreme_channels,
            [["1e999"]],
            [[Decimal("1e999")]],
            exact_extreme_cofactor,
        ) == [[repr(math.asinh(1.0))]]
        checks += 1
        exact_tiny_cofactor = {"A": ("1e-999", Decimal("1e-999"))}
        assert transform_events(
            exact_extreme_channels,
            [["1e-999"]],
            [[Decimal("1e-999")]],
            exact_tiny_cofactor,
        ) == [[repr(math.asinh(1.0))]]
        checks += 1
        expect(
            "numeric-overflow",
            lambda: transform_events(
                exact_extreme_channels,
                [["1e999"]],
                [[Decimal("1e999")]],
                exact_tiny_cofactor,
            ),
            "needs-tool",
        )
        expect(
            "numeric-underflow",
            lambda: transform_events(
                exact_extreme_channels,
                [["1e-999"]],
                [[Decimal("1e-999")]],
                exact_extreme_cofactor,
            ),
            "needs-tool",
        )
        expect(
            "numeric-underflow",
            lambda: transform_events(
                exact_extreme_channels,
                [["1e-999999"]],
                [[Decimal("1e-999999")]],
                {"A": ("1e999999", Decimal("1e999999"))},
            ),
            "needs-tool",
        )
        embedded = b'event_id\tFITC-A\n"e\n1"\t1\n'
        expect("invalid-character", lambda: decode_tsv(embedded, "embedded-line-break"))
        duplicate_events = decode_tsv(b"event_id\tFITC-A\ne1\t1\ne1\t2\n", "duplicate-events")
        expect("invalid-event-id", lambda: parse_events(duplicate_events))
        empty_events = decode_tsv(b"event_id\tFITC-A\n", "empty-events")
        expect("empty-events", lambda: parse_events(empty_events))

        fifo = root / "events.fifo"
        os.mkfifo(fifo)
        expect("input-not-regular", lambda: read_stable(str(fifo)))
        link = root / "events-link.tsv"
        link.symlink_to(events)
        expect("input-symlink", lambda: read_stable(str(link)))
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

        short_one = root / "short-one.bin"
        short_two = root / "short-two.bin"
        original_write = os.write

        def short_write(descriptor: int, data: bytes) -> int:
            return original_write(descriptor, data[:5])

        os.write = short_write
        try:
            publish_pair(short_one, b"abcdefghij" * 11, short_two, b"0123456789" * 13)
        finally:
            os.write = original_write
        assert short_one.read_bytes() == b"abcdefghij" * 11
        assert short_two.read_bytes() == b"0123456789" * 13
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
        expect(
            "output-collision",
            lambda: publish_pair(root / "same.bin", b"one", root / "same.bin", b"two"),
            "invalid-output",
        )
        assert not any(path.name.startswith(".") for path in root.iterdir())
        checks += 1
    return {"checks": checks, "status": "pass", "version": VERSION}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--events")
    result.add_argument("--cofactors")
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
    required = ("events", "cofactors", "output_events", "output_report")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        print(
            json.dumps(
                {
                    "status": "invalid-input",
                    "analysis_performed": False,
                    "code": "missing-argument",
                    "missing": missing,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        print(
            json.dumps(
                execute(args.events, args.cofactors, args.output_events, args.output_report),
                sort_keys=True,
            )
        )
        return 0
    except ContractError as exc:
        print(
            json.dumps(
                {
                    "status": exc.status,
                    "analysis_performed": False,
                    "code": exc.code,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3 if exc.status in {"needs-tool", "io-error"} else 2
    except OSError as exc:
        print(
            json.dumps(
                {
                    "status": "io-error",
                    "analysis_performed": False,
                    "code": "io-error",
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
