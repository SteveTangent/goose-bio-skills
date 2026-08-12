#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded, deterministic QC report for local chromatin peak sets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator


VERSION = "0.7.0"
MIB = 1024 * 1024
MAX_INPUT_BYTES = 16 * MIB
MAX_LINE_BYTES = 64 * 1024
MAX_DATA_ROWS_PER_FILE = 250_000
MAX_TOTAL_PEAK_ROWS = 500_000
MAX_PEAK_FILES = 4
MAX_BUILD_LABEL_BYTES = 128
MAX_DUPLICATE_EXAMPLES = 10
MAX_INTEGER = 2**63 - 1
INTEGER_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)")


class ContractError(Exception):
    """The requested report cannot safely or completely run."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: str = "invalid-input",
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.path = path

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True, order=True)
class Interval:
    contig: str
    start: int
    end: int


def lexical_absolute(raw: str) -> Path:
    if not raw or "\x00" in raw:
        raise ContractError("invalid-path", "path must be non-empty and contain no NUL byte")
    supplied = Path(raw)
    if ".." in supplied.parts:
        raise ContractError("parent-traversal", "parent traversal is forbidden", path=raw)
    return Path(os.path.abspath(os.fspath(supplied)))


def lstat_regular(path: Path) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise ContractError("path-not-found", "input does not exist", path=str(path)) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ContractError("symlink-refused", "input must not be a leaf symlink", path=str(path))
    if not stat.S_ISREG(metadata.st_mode):
        raise ContractError("not-regular-file", "input must be a regular file", path=str(path))
    if metadata.st_size > MAX_INPUT_BYTES:
        raise ContractError(
            "input-too-large",
            f"input exceeds the {MAX_INPUT_BYTES}-byte package limit",
            status="needs-tool",
            path=str(path),
        )
    return metadata


@contextmanager
def bounded_binary_input(raw_path: str) -> Iterator[tuple[Path, os.stat_result, BinaryIO]]:
    path = lexical_absolute(raw_path)
    before = lstat_regular(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContractError("input-open-failed", str(exc), path=str(path)) from exc
    handle: BinaryIO | None = None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ContractError("not-regular-file", "input did not open as a regular file", path=str(path))
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ContractError("input-changed", "input changed while opening", path=str(path))
        handle = os.fdopen(descriptor, "rb")
        descriptor = -1
        yield path, opened, handle
        try:
            after_open = os.fstat(handle.fileno())
            after_path = os.lstat(path)
        except OSError as exc:
            raise ContractError(
                "input-changed",
                "input changed during analysis",
                path=str(path),
            ) from exc
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if stat.S_ISLNK(after_path.st_mode) or any(
            getattr(opened, field) != getattr(after_open, field)
            or getattr(after_open, field) != getattr(after_path, field)
            for field in stable
        ):
            raise ContractError("input-changed", "input changed during analysis", path=str(path))
    finally:
        if handle is not None:
            handle.close()
        elif descriptor >= 0:
            os.close(descriptor)


def validate_build(label: str, role: str) -> None:
    encoded = label.encode("utf-8", errors="strict")
    if (
        not label
        or label != label.strip()
        or len(encoded) > MAX_BUILD_LABEL_BYTES
        or any(not character.isprintable() for character in label)
    ):
        raise ContractError(
            "invalid-build-declaration",
            f"{role} build must be a non-empty printable exact label without outer whitespace",
        )


def validate_token(token: str, label: str, line_number: int) -> None:
    if not token or token != token.strip() or any(
        character.isspace() or not character.isprintable() for character in token
    ):
        raise ContractError("invalid-token", f"{label} is invalid at line {line_number}")


def parse_nonnegative_integer(token: str, label: str, line_number: int) -> int:
    if not INTEGER_TOKEN.fullmatch(token):
        raise ContractError("invalid-integer", f"{label} is invalid at line {line_number}")
    maximum = str(MAX_INTEGER)
    if len(token) > len(maximum) or (len(token) == len(maximum) and token > maximum):
        raise ContractError("integer-too-large", f"{label} is too large at line {line_number}")
    return int(token)


def parse_finite(token: str, label: str, line_number: int) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise ContractError("invalid-number", f"{label} is invalid at line {line_number}") from exc
    if not math.isfinite(value):
        raise ContractError("non-finite-number", f"{label} is non-finite at line {line_number}")
    return value


def parse_data_lines(
    raw_path: str,
    expected_columns: int,
    row_parser: Any,
) -> tuple[list[Any], dict[str, Any]]:
    digest = hashlib.sha256()
    rows: list[Any] = []
    line_count = 0
    with bounded_binary_input(raw_path) as (_, metadata, handle):
        for line_number, raw in enumerate(handle, 1):
            line_count = line_number
            if len(raw) > MAX_LINE_BYTES:
                raise ContractError(
                    "line-too-long",
                    f"line {line_number} exceeds {MAX_LINE_BYTES} bytes",
                    status="needs-tool",
                )
            digest.update(raw)
            try:
                text = raw.rstrip(b"\r\n").decode("ascii")
            except UnicodeDecodeError as exc:
                raise ContractError("non-ascii-input", f"non-ASCII byte at line {line_number}") from exc
            if not text or text.startswith("#"):
                continue
            fields = text.split("\t")
            if len(fields) != expected_columns:
                raise ContractError(
                    "invalid-column-count",
                    f"expected {expected_columns} tab-separated fields at line {line_number}, got {len(fields)}",
                )
            rows.append(row_parser(fields, line_number))
            if len(rows) > MAX_DATA_ROWS_PER_FILE:
                raise ContractError(
                    "too-many-data-rows",
                    f"input exceeds {MAX_DATA_ROWS_PER_FILE} data rows",
                    status="needs-tool",
                )
    return rows, {
        "sha256": digest.hexdigest(),
        "size_bytes": metadata.st_size,
        "line_count": line_count,
        "data_row_count": len(rows),
    }


def parse_contig_sizes(raw_path: str) -> tuple[dict[str, int], dict[str, Any]]:
    def parse(fields: list[str], line_number: int) -> tuple[str, int]:
        contig, raw_size = fields
        validate_token(contig, "contig", line_number)
        size = parse_nonnegative_integer(raw_size, "contig size", line_number)
        if size == 0:
            raise ContractError("invalid-contig-size", f"contig size must be positive at line {line_number}")
        return contig, size

    parsed, details = parse_data_lines(raw_path, 2, parse)
    if not parsed:
        raise ContractError("empty-contig-sizes", "contig-size file has no data rows")
    sizes: dict[str, int] = {}
    for contig, size in parsed:
        if contig in sizes:
            raise ContractError("duplicate-contig", f"contig {contig!r} is duplicated")
        sizes[contig] = size
    details.update({"contig_count": len(sizes), "total_reference_bases": sum(sizes.values())})
    return sizes, details


def parse_interval_fields(
    fields: list[str],
    line_number: int,
    contig_sizes: dict[str, int],
) -> Interval:
    contig, raw_start, raw_end = fields[:3]
    validate_token(contig, "contig", line_number)
    start = parse_nonnegative_integer(raw_start, "start", line_number)
    end = parse_nonnegative_integer(raw_end, "end", line_number)
    if end <= start:
        raise ContractError(
            "invalid-interval-width",
            f"interval must have positive half-open width at line {line_number}",
        )
    if contig not in contig_sizes:
        raise ContractError("unknown-contig", f"contig {contig!r} is absent from contig sizes at line {line_number}")
    if end > contig_sizes[contig]:
        raise ContractError(
            "interval-out-of-range",
            f"end exceeds declared size for {contig!r} at line {line_number}",
        )
    return Interval(contig, start, end)


def validate_narrowpeak_fields(fields: list[str], line_number: int, interval: Interval) -> None:
    name, raw_score, strand, raw_signal, raw_p, raw_q, raw_peak = fields[3:10]
    if not name or any(not character.isprintable() for character in name):
        raise ContractError("invalid-peak-name", f"name is invalid at line {line_number}")
    score = parse_nonnegative_integer(raw_score, "score", line_number)
    if score > 1000:
        raise ContractError("invalid-score", f"score must be in [0, 1000] at line {line_number}")
    if strand not in {"+", "-", "."}:
        raise ContractError("invalid-strand", f"strand must be +, -, or . at line {line_number}")
    if parse_finite(raw_signal, "signalValue", line_number) < 0:
        raise ContractError("invalid-signal-value", f"signalValue must be nonnegative at line {line_number}")
    for label, token in (("pValue", raw_p), ("qValue", raw_q)):
        if token != "-1" and parse_finite(token, label, line_number) < 0:
            raise ContractError(
                "invalid-significance-value",
                f"{label} must be -1 or nonnegative at line {line_number}",
            )
    if raw_peak == "-1":
        return
    peak = parse_nonnegative_integer(raw_peak, "peak", line_number)
    if peak >= interval.end - interval.start:
        raise ContractError(
            "invalid-peak-offset",
            f"peak offset must be -1 or within the half-open interval at line {line_number}",
        )


def merge_intervals(intervals: list[Interval]) -> dict[str, list[tuple[int, int]]]:
    merged: dict[str, list[tuple[int, int]]] = {}
    for interval in sorted(set(intervals)):
        contig_rows = merged.setdefault(interval.contig, [])
        if not contig_rows or interval.start > contig_rows[-1][1]:
            contig_rows.append((interval.start, interval.end))
        else:
            start, end = contig_rows[-1]
            contig_rows[-1] = (start, max(end, interval.end))
    return merged


def merged_coverage(merged: dict[str, list[tuple[int, int]]]) -> int:
    return sum(end - start for rows in merged.values() for start, end in rows)


def interval_summary(intervals: list[Interval], merged: dict[str, list[tuple[int, int]]]) -> dict[str, Any]:
    widths = [interval.end - interval.start for interval in intervals]
    coordinates = Counter((interval.contig, interval.start, interval.end) for interval in intervals)
    duplicate_examples = [
        {"contig": contig, "start": start, "end": end, "row_count": count}
        for (contig, start, end), count in sorted(coordinates.items())
        if count > 1
    ][:MAX_DUPLICATE_EXAMPLES]
    return {
        "interval_count": len(intervals),
        "contig_count": len({interval.contig for interval in intervals}),
        "duplicate_coordinate_count": sum(count - 1 for count in coordinates.values() if count > 1),
        "duplicate_coordinate_examples": duplicate_examples,
        "minimum_width_bases": min(widths),
        "maximum_width_bases": max(widths),
        "total_row_width_bases": sum(widths),
        "merged_interval_count": sum(len(rows) for rows in merged.values()),
        "merged_coverage_bases": merged_coverage(merged),
    }


def parse_peak_file(
    raw_path: str,
    peak_format: str,
    contig_sizes: dict[str, int],
) -> tuple[list[Interval], dict[str, list[tuple[int, int]]], dict[str, Any]]:
    if peak_format not in {"bed", "narrowPeak"}:
        raise ContractError("invalid-peak-format", "peak format must be bed or narrowPeak")
    expected_columns = 3 if peak_format == "bed" else 10

    def parse(fields: list[str], line_number: int) -> Interval:
        interval = parse_interval_fields(fields, line_number, contig_sizes)
        if peak_format == "narrowPeak":
            validate_narrowpeak_fields(fields, line_number, interval)
        return interval

    intervals, details = parse_data_lines(raw_path, expected_columns, parse)
    if not intervals:
        raise ContractError("empty-peak-file", "peak file has no data rows")
    merged = merge_intervals(intervals)
    return intervals, merged, details


def parse_blacklist(
    raw_path: str,
    contig_sizes: dict[str, int],
) -> tuple[list[Interval], dict[str, list[tuple[int, int]]], dict[str, Any]]:
    def parse(fields: list[str], line_number: int) -> Interval:
        return parse_interval_fields(fields, line_number, contig_sizes)

    intervals, details = parse_data_lines(raw_path, 3, parse)
    if not intervals:
        raise ContractError("empty-blacklist", "blacklist has no data rows")
    merged = merge_intervals(intervals)
    return intervals, merged, details


def intersection_length(
    left: dict[str, list[tuple[int, int]]],
    right: dict[str, list[tuple[int, int]]],
) -> int:
    total = 0
    for contig in sorted(set(left).intersection(right)):
        left_rows = left[contig]
        right_rows = right[contig]
        i = 0
        j = 0
        while i < len(left_rows) and j < len(right_rows):
            left_start, left_end = left_rows[i]
            right_start, right_end = right_rows[j]
            total += max(0, min(left_end, right_end) - max(left_start, right_start))
            if left_end <= right_end:
                i += 1
            if right_end <= left_end:
                j += 1
    return total


def blacklist_row_hits(
    intervals: list[Interval],
    blacklist: dict[str, list[tuple[int, int]]],
) -> int:
    hits = 0
    by_contig: dict[str, list[Interval]] = {}
    for interval in intervals:
        by_contig.setdefault(interval.contig, []).append(interval)
    for contig, rows in by_contig.items():
        blocked = blacklist.get(contig, [])
        cursor = 0
        for interval in sorted(rows):
            while cursor < len(blocked) and blocked[cursor][1] <= interval.start:
                cursor += 1
            if cursor < len(blocked) and blocked[cursor][0] < interval.end:
                hits += 1
    return hits


def validate_request(
    contig_build: str,
    peak_paths: list[str],
    peak_formats: list[str],
    peak_builds: list[str],
    blacklist_path: str | None,
    blacklist_build: str | None,
) -> None:
    validate_build(contig_build, "contig-size")
    if not 1 <= len(peak_paths) <= MAX_PEAK_FILES:
        raise ContractError("invalid-peak-count", f"provide one to {MAX_PEAK_FILES} peak files")
    if len(peak_formats) != len(peak_paths) or len(peak_builds) != len(peak_paths):
        raise ContractError(
            "unaligned-peak-declarations",
            "provide exactly one --peak-format and --peak-build for every --peak, in the same order",
        )
    for index, (peak_format, peak_build) in enumerate(zip(peak_formats, peak_builds), 1):
        if peak_format not in {"bed", "narrowPeak"}:
            raise ContractError("invalid-peak-format", f"peak set {index} format must be bed or narrowPeak")
        validate_build(peak_build, f"peak set {index}")
        if peak_build != contig_build:
            raise ContractError(
                "build-mismatch",
                f"peak set {index} build does not exactly match the contig-size build",
            )
    if (blacklist_path is None) != (blacklist_build is None):
        raise ContractError(
            "incomplete-blacklist-declaration",
            "--blacklist and --blacklist-build must be supplied together",
        )
    if blacklist_build is not None:
        validate_build(blacklist_build, "blacklist")
        if blacklist_build != contig_build:
            raise ContractError("build-mismatch", "blacklist build does not exactly match the contig-size build")


def build_report(
    contig_sizes_path: str,
    contig_build: str,
    peak_paths: list[str],
    peak_formats: list[str],
    peak_builds: list[str],
    blacklist_path: str | None = None,
    blacklist_build: str | None = None,
) -> dict[str, Any]:
    validate_request(
        contig_build,
        peak_paths,
        peak_formats,
        peak_builds,
        blacklist_path,
        blacklist_build,
    )
    contig_sizes, contig_details = parse_contig_sizes(contig_sizes_path)
    parsed_sets: list[tuple[list[Interval], dict[str, list[tuple[int, int]]]]] = []
    peak_reports: list[dict[str, Any]] = []
    total_peak_rows = 0
    for index, (path, peak_format, peak_build) in enumerate(
        zip(peak_paths, peak_formats, peak_builds), 1
    ):
        intervals, merged, details = parse_peak_file(path, peak_format, contig_sizes)
        total_peak_rows += len(intervals)
        if total_peak_rows > MAX_TOTAL_PEAK_ROWS:
            raise ContractError(
                "too-many-total-peak-rows",
                f"run exceeds {MAX_TOTAL_PEAK_ROWS} total peak rows",
                status="needs-tool",
            )
        parsed_sets.append((intervals, merged))
        peak_reports.append(
            {
                "peak_set_index": index,
                "format": peak_format,
                "declared_build": peak_build,
                "input": details,
                "summary": interval_summary(intervals, merged),
            }
        )

    blacklist_report: dict[str, Any] | None = None
    blacklist_merged: dict[str, list[tuple[int, int]]] | None = None
    if blacklist_path is not None:
        blacklist_intervals, blacklist_merged, blacklist_details = parse_blacklist(
            blacklist_path, contig_sizes
        )
        blacklist_report = {
            "declared_build": blacklist_build,
            "format": "bed",
            "input": blacklist_details,
            "summary": interval_summary(blacklist_intervals, blacklist_merged),
        }
        for peak_report, (intervals, merged) in zip(peak_reports, parsed_sets):
            peak_report["blacklist_overlap"] = {
                "input_rows_overlapping_blacklist": blacklist_row_hits(intervals, blacklist_merged),
                "merged_coverage_overlap_bases": intersection_length(merged, blacklist_merged),
            }

    pairwise: list[dict[str, Any]] = []
    for left_index in range(len(parsed_sets)):
        left_coverage = merged_coverage(parsed_sets[left_index][1])
        for right_index in range(left_index + 1, len(parsed_sets)):
            right_coverage = merged_coverage(parsed_sets[right_index][1])
            intersection = intersection_length(parsed_sets[left_index][1], parsed_sets[right_index][1])
            union = left_coverage + right_coverage - intersection
            pairwise.append(
                {
                    "peak_set_a": left_index + 1,
                    "peak_set_b": right_index + 1,
                    "intersection_bases": intersection,
                    "union_bases": union,
                    "jaccard": round(intersection / union, 12),
                }
            )

    return {
        "schema_version": "0.1.0",
        "tool": "check_peak_sets.py",
        "tool_version": VERSION,
        "status": "completed",
        "analysis": "chromatin-peak-set-qc",
        "reference": {
            "declared_build": contig_build,
            "build_identity_status": "caller-declared-not-independently-verified",
            "coordinate_system": "zero-based-half-open",
            "contig_sizes": contig_details,
        },
        "peak_sets": peak_reports,
        "blacklist": blacklist_report,
        "pairwise_base_coverage": pairwise,
        "limits": {
            "max_peak_files": MAX_PEAK_FILES,
            "max_input_bytes_per_file": MAX_INPUT_BYTES,
            "max_line_bytes": MAX_LINE_BYTES,
            "max_data_rows_per_file": MAX_DATA_ROWS_PER_FILE,
            "max_total_peak_rows": MAX_TOTAL_PEAK_ROWS,
            "network": False,
            "subprocess": False,
            "compression": False,
        },
        "limitations": [
            "Build identity and blacklist provenance are caller declarations and are not independently verified.",
            "BED means exact BED3; narrowPeak means exact ten-field narrowPeak.",
            "Pairwise Jaccard is descriptive merged half-open base coverage and does not establish reproducibility or quality.",
            "The report does not perform read QC, peak calling, FRiP, IDR, consensus construction, differential accessibility, motif analysis, or lift-over.",
        ],
    }


def output_target(raw_path: str | Path, root: Path | None = None) -> tuple[Path, Path, tuple[str, ...]]:
    raw_text = os.fspath(raw_path)
    if not raw_text or "\x00" in raw_text:
        raise ContractError("invalid-path", "output path must be non-empty and contain no NUL byte")
    supplied = Path(raw_text)
    if ".." in supplied.parts:
        raise ContractError("parent-traversal", "output parent traversal is forbidden", path=raw_text)

    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    try:
        root_state = os.lstat(lexical_root)
    except FileNotFoundError as exc:
        raise ContractError("output-root-missing", "output root does not exist", path=str(lexical_root)) from exc
    if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
        raise ContractError("unsafe-output-root", "output root must be a real directory", path=str(lexical_root))
    if supplied.is_absolute():
        candidate = Path(os.path.abspath(supplied))
    else:
        candidate = lexical_root / supplied
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise ContractError(
            "output-outside-root",
            "output must remain under the current working directory",
            path=str(candidate),
        ) from exc
    if not relative.parts:
        raise ContractError("output-not-file", "output must name a file", path=str(candidate))
    return lexical_root, candidate, relative.parts


def open_output_parent(raw_path: str | Path, root: Path | None = None) -> tuple[Path, int, str]:
    lexical_root, candidate, parts = output_target(raw_path, root)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lexical_root, flags)
    except OSError as exc:
        raise ContractError(
            "unsafe-output-root",
            "output root changed or is unsafe",
            path=str(lexical_root),
        ) from exc
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError as exc:
                raise ContractError(
                    "output-parent-missing",
                    "output parent must already exist",
                    path=str(candidate.parent),
                ) from exc
            except OSError as exc:
                raise ContractError(
                    "output-parent-symlink",
                    "output parent changed or contains a symlink",
                    path=str(candidate.parent),
                ) from exc
            os.close(descriptor)
            descriptor = child
        try:
            target_state = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            code = "output-symlink-refused" if stat.S_ISLNK(target_state.st_mode) else "output-exists"
            raise ContractError(code, "output exists; overwrite is forbidden", path=str(candidate))
        return candidate, descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def safe_output_target(raw_path: str | Path, root: Path | None = None) -> Path:
    target, directory_fd, _ = open_output_parent(raw_path, root)
    os.close(directory_fd)
    return target


def unlink_owned_at(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def write_new_json(
    raw_path: str | Path,
    report: dict[str, Any],
    *,
    root: Path | None = None,
    before_publish: Callable[[], None] | None = None,
) -> Path:
    target, directory_fd, target_name = open_output_parent(raw_path, root)
    payload = (
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
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
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
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
            raise ContractError("output-exists", "output appeared; overwrite is forbidden", path=str(target)) from exc
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


def expect_error(code: str, action: Any) -> None:
    try:
        action()
    except ContractError as exc:
        if exc.code != code:
            raise RuntimeError(f"expected {code}, got {exc.code}") from exc
    else:
        raise RuntimeError(f"expected {code}")


def require_test(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def self_test() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="bio02-peak-set-qc-") as temporary:
        root = Path(temporary)
        contigs = root / "tiny.chrom.sizes"
        contigs.write_text("chr1\t1000\nchr2\t500\n", encoding="ascii")
        blacklist = root / "blacklist.bed"
        blacklist.write_text("chr1\t180\t200\n", encoding="ascii")
        first = root / "first.narrowPeak"
        first.write_text(
            "chr1\t100\t200\tp1\t100\t.\t10\t5\t4\t50\n"
            "chr1\t100\t200\tp1-duplicate\t90\t.\t9\t4\t3\t75\n"
            "chr1\t300\t350\tp2\t80\t+\t8\t-1\t-1\t-1\n"
            "chr2\t0\t50\tp3\t70\t-\t7\t3\t2\t10\n",
            encoding="ascii",
        )
        second = root / "second.bed"
        second.write_text("chr1\t150\t250\nchr1\t300\t400\nchr2\t40\t60\n", encoding="ascii")

        report = build_report(
            str(contigs),
            "GRCh38-test",
            [str(first), str(second)],
            ["narrowPeak", "bed"],
            ["GRCh38-test", "GRCh38-test"],
            str(blacklist),
            "GRCh38-test",
        )
        require_test(report["reference"]["build_identity_status"] == "caller-declared-not-independently-verified", "build disclosure differs")
        require_test(report["peak_sets"][0]["summary"]["duplicate_coordinate_count"] == 1, "duplicate count differs")
        require_test(report["peak_sets"][0]["summary"]["merged_coverage_bases"] == 200, "first coverage differs")
        require_test(report["peak_sets"][1]["summary"]["merged_coverage_bases"] == 220, "second coverage differs")
        require_test(report["peak_sets"][0]["blacklist_overlap"] == {"input_rows_overlapping_blacklist": 2, "merged_coverage_overlap_bases": 20}, "first blacklist result differs")
        require_test(report["pairwise_base_coverage"] == [{"peak_set_a": 1, "peak_set_b": 2, "intersection_bases": 110, "union_bases": 310, "jaccard": 0.354838709677}], "pairwise Jaccard differs")
        require_test(report == build_report(str(contigs), "GRCh38-test", [str(first), str(second)], ["narrowPeak", "bed"], ["GRCh38-test", "GRCh38-test"], str(blacklist), "GRCh38-test"), "report is not deterministic")
        checks += 7

        output = root / "report.json"
        write_new_json(output, report, root=root)
        second_output = root / "report-copy.json"
        write_new_json(second_output, report, root=root)
        require_test(output.read_bytes() == second_output.read_bytes(), "published JSON bytes differ")
        expect_error("output-exists", lambda: write_new_json(output, report, root=root))
        expect_error("parent-traversal", lambda: write_new_json(Path("..") / "escape.json", report, root=root))
        expect_error("output-outside-root", lambda: write_new_json(root.parent / "outside.json", report, root=root))
        checks += 4

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        expect_error("output-parent-symlink", lambda: write_new_json(linked_parent / "report.json", report, root=root))
        checks += 1

        swap_parent = root / "swap-parent"
        swap_parent.mkdir()
        held_parent = root / "held-parent"
        with tempfile.TemporaryDirectory(prefix="peak-qc-outside-") as outside_name:
            outside = Path(outside_name)

            def swap_output_parent() -> None:
                swap_parent.rename(held_parent)
                swap_parent.symlink_to(outside, target_is_directory=True)

            write_new_json(
                Path("swap-parent") / "report.json",
                report,
                root=root,
                before_publish=swap_output_parent,
            )
            require_test(not (outside / "report.json").exists(), "output-parent swap escaped root")
            require_test((held_parent / "report.json").is_file(), "held output-parent publication differs")
            swap_parent.unlink()
            held_parent.rename(swap_parent)
        checks += 1

        nested_root = root / "nested-output-root"
        nested_root.mkdir()
        held_root = root / "held-output-root"
        with tempfile.TemporaryDirectory(prefix="peak-qc-root-outside-") as outside_name:
            outside = Path(outside_name)

            def swap_output_root() -> None:
                nested_root.rename(held_root)
                nested_root.symlink_to(outside, target_is_directory=True)

            write_new_json(
                "report.json",
                report,
                root=nested_root,
                before_publish=swap_output_root,
            )
            require_test(not (outside / "report.json").exists(), "output-root swap escaped root")
            require_test((held_root / "report.json").is_file(), "held output-root publication differs")
            nested_root.unlink()
            held_root.rename(nested_root)
        checks += 1

        fsync_output = root / "fsync-report.json"
        real_fsync = os.fsync

        def fail_directory_fsync(descriptor: int) -> None:
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("injected directory fsync failure")
            real_fsync(descriptor)

        os.fsync = fail_directory_fsync
        try:
            write_new_json(fsync_output, report, root=root)
        finally:
            os.fsync = real_fsync
        require_test(fsync_output.is_file(), "post-commit fsync publication differs")
        checks += 1

        expect_error("build-mismatch", lambda: build_report(str(contigs), "GRCh38-test", [str(first), str(second)], ["narrowPeak", "bed"], ["GRCh38-test", "hg19"]))
        expect_error("invalid-peak-count", lambda: build_report(str(contigs), "GRCh38-test", [str(second)] * 5, ["bed"] * 5, ["GRCh38-test"] * 5))
        checks += 2

        expect_error(
            "integer-too-large",
            lambda: parse_nonnegative_integer("9" * 5000, "start", 1),
        )
        checks += 1

        invalid_peak = root / "invalid-peak.narrowPeak"
        invalid_peak.write_text("chr1\t100\t200\tp\t1\t.\t1\t-1\t-1\t100\n", encoding="ascii")
        expect_error("invalid-peak-offset", lambda: build_report(str(contigs), "GRCh38-test", [str(invalid_peak)], ["narrowPeak"], ["GRCh38-test"]))
        malformed = root / "malformed.bed"
        malformed.write_text("chr1\t10\t20\textra\n", encoding="ascii")
        expect_error("invalid-column-count", lambda: build_report(str(contigs), "GRCh38-test", [str(malformed)], ["bed"], ["GRCh38-test"]))
        out_of_range = root / "out-of-range.bed"
        out_of_range.write_text("chr1\t999\t1001\n", encoding="ascii")
        expect_error("interval-out-of-range", lambda: build_report(str(contigs), "GRCh38-test", [str(out_of_range)], ["bed"], ["GRCh38-test"]))
        checks += 3

        if hasattr(os, "symlink"):
            input_link = root / "input-link.bed"
            input_link.symlink_to(second)
            expect_error("symlink-refused", lambda: build_report(str(contigs), "GRCh38-test", [str(input_link)], ["bed"], ["GRCh38-test"]))
            output_link = root / "output-link.json"
            output_link.symlink_to(output)
            expect_error("output-symlink-refused", lambda: write_new_json(output_link, report, root=root))
            checks += 2

        vanishing = root / "vanishing.bed"
        vanishing.write_text("chr1\t10\t20\n", encoding="ascii")

        def remove_open_input() -> None:
            with bounded_binary_input(str(vanishing)) as (_, _, handle):
                handle.read()
                vanishing.unlink()

        expect_error("input-changed", remove_open_input)
        checks += 1

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Check bounded local BED3 or narrowPeak files under one exact declared build."
    )
    command.add_argument("--contig-sizes")
    command.add_argument("--contig-build")
    command.add_argument("--peak", action="append", default=[])
    command.add_argument("--peak-format", action="append", default=[])
    command.add_argument("--peak-build", action="append", default=[])
    command.add_argument("--blacklist")
    command.add_argument("--blacklist-build")
    command.add_argument("--output")
    command.add_argument("--self-test", action="store_true")
    command.add_argument("--version", action="version", version=VERSION)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    missing = [
        option
        for option, value in (
            ("contig-sizes", args.contig_sizes),
            ("contig-build", args.contig_build),
            ("peak", args.peak),
            ("peak-format", args.peak_format),
            ("peak-build", args.peak_build),
            ("output", args.output),
        )
        if not value
    ]
    if missing:
        print(
            json.dumps(
                {
                    "error": {"code": "missing-argument", "message": f"missing: {', '.join(missing)}"},
                    "status": "needs-decision",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        safe_output_target(args.output)
        report = build_report(
            args.contig_sizes,
            args.contig_build,
            args.peak,
            args.peak_format,
            args.peak_build,
            args.blacklist,
            args.blacklist_build,
        )
        output = write_new_json(args.output, report)
    except ContractError as exc:
        print(
            json.dumps({"error": exc.as_dict(), "status": exc.status}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"output": str(output), "status": "completed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
