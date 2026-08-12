#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Calculate descriptive PSI and a declared two-group delta from prepared counts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
from typing import Any, Sequence


MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_DATA_ROWS = 200_000
MAX_COUNT = 2**63 - 1
MAX_LABEL_CHARS = 256
COUNT_HEADERS = ["event_id", "sample_id", "inclusion_count", "exclusion_count"]
GROUP_HEADERS = ["sample_id", "group"]
CANONICAL_INTEGER = re.compile(r"0|[1-9][0-9]*")


class UserError(Exception):
    """A bounded, user-correctable input or publication error."""

    def __init__(
        self, code: str, message: str, status: str = "invalid-input"
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class InputBlob:
    label: str
    name: str
    data: bytes
    sha256: str
    device: int
    inode: int


def _stat_signature(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_regular_leaf(path_text: str, label: str) -> InputBlob:
    """Read bounded bytes from one pinned regular leaf; parent symlinks are allowed."""
    path = Path(path_text).expanduser()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    before_lstat: os.stat_result | None = None

    if not nofollow:
        try:
            before_lstat = os.lstat(path)
        except OSError as exc:
            raise UserError("input-open-failed", f"cannot inspect {label} input") from exc
        if stat.S_ISLNK(before_lstat.st_mode):
            raise UserError("input-leaf-symlink", f"{label} input leaf must not be a symlink")

    try:
        descriptor = os.open(path, flags | nofollow)
    except OSError as exc:
        raise UserError(
            "input-open-failed",
            f"cannot open {label} as a regular non-symlinked input leaf",
        ) from exc

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise UserError("input-not-regular", f"{label} input must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise UserError(
                "input-too-large",
                f"{label} input exceeds the {MAX_INPUT_BYTES}-byte limit",
            )

        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_INPUT_BYTES:
                raise UserError(
                    "input-too-large",
                    f"{label} input exceeds the {MAX_INPUT_BYTES}-byte limit",
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    if _stat_signature(before) != _stat_signature(after) or size != after.st_size:
        raise UserError("input-changed", f"{label} input changed while it was read")

    if before_lstat is not None:
        try:
            after_lstat = os.lstat(path)
        except OSError as exc:
            raise UserError("input-changed", f"{label} input changed while it was read") from exc
        if (
            stat.S_ISLNK(after_lstat.st_mode)
            or before_lstat.st_dev != after_lstat.st_dev
            or before_lstat.st_ino != after_lstat.st_ino
            or after_lstat.st_dev != after.st_dev
            or after_lstat.st_ino != after.st_ino
        ):
            raise UserError("input-changed", f"{label} input changed while it was read")

    data = b"".join(chunks)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UserError("input-not-utf8", f"{label} input must be valid UTF-8") from exc
    if b"\x00" in data:
        raise UserError("input-nul-byte", f"{label} input contains a NUL byte")

    return InputBlob(
        label=label,
        name=path.name,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        device=after.st_dev,
        inode=after.st_ino,
    )


def parse_tsv(blob: InputBlob, expected_headers: list[str]) -> list[list[str]]:
    text = blob.data.decode("utf-8")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        rows = list(reader)
    except csv.Error as exc:
        raise UserError("malformed-tsv", f"{blob.label} input is not valid TSV") from exc

    if not rows:
        raise UserError("empty-input", f"{blob.label} input is empty")
    if rows[0] != expected_headers:
        raise UserError(
            "invalid-header",
            f"{blob.label} header must be exactly: {', '.join(expected_headers)}",
        )
    if len(rows) - 1 > MAX_DATA_ROWS:
        raise UserError(
            "too-many-rows",
            f"{blob.label} input exceeds the {MAX_DATA_ROWS}-row limit",
        )

    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(expected_headers) or all(value == "" for value in row):
            raise UserError(
                "invalid-row",
                f"{blob.label} line {line_number} must contain exactly {len(expected_headers)} fields",
            )
    return rows[1:]


def validate_label(value: str, field: str, line_number: int | None = None) -> str:
    location = f" on line {line_number}" if line_number is not None else ""
    if not value or value != value.strip():
        raise UserError("invalid-label", f"{field}{location} must be nonempty without edge whitespace")
    if len(value) > MAX_LABEL_CHARS:
        raise UserError(
            "invalid-label",
            f"{field}{location} exceeds the {MAX_LABEL_CHARS}-character limit",
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise UserError("invalid-label", f"{field}{location} contains a control character")
    return value


def parse_nonnegative_integer(value: str, field: str, line_number: int) -> int:
    if not CANONICAL_INTEGER.fullmatch(value):
        raise UserError(
            "invalid-count",
            f"{field} on line {line_number} must be a canonical nonnegative integer",
        )
    result = int(value)
    if result > MAX_COUNT:
        raise UserError("count-too-large", f"{field} on line {line_number} exceeds 2^63 - 1")
    return result


def parse_minimum_coverage(value: str) -> int:
    if not CANONICAL_INTEGER.fullmatch(value):
        raise UserError("invalid-minimum-coverage", "minimum coverage must be a canonical integer")
    result = int(value)
    if result < 1 or result > MAX_COUNT:
        raise UserError("invalid-minimum-coverage", "minimum coverage must be between 1 and 2^63 - 1")
    return result


def load_groups(
    rows: list[list[str]], group_a: str, group_b: str
) -> tuple[list[str], dict[str, str]]:
    if group_a == group_b:
        raise UserError("ambiguous-groups", "group A and group B must be distinct")

    sample_order: list[str] = []
    groups: dict[str, str] = {}
    group_sizes = {group_a: 0, group_b: 0}
    for line_number, row in enumerate(rows, start=2):
        sample_id = validate_label(row[0], "sample_id", line_number)
        group = validate_label(row[1], "group", line_number)
        if sample_id in groups:
            raise UserError("duplicate-sample", f"groups line {line_number} repeats sample_id {sample_id!r}")
        if group not in group_sizes:
            raise UserError(
                "unexpected-group",
                f"groups line {line_number} uses a label outside the two declared groups",
            )
        sample_order.append(sample_id)
        groups[sample_id] = group
        group_sizes[group] += 1

    if not sample_order:
        raise UserError("empty-groups", "groups input contains no samples")
    if group_sizes[group_a] == 0 or group_sizes[group_b] == 0:
        raise UserError("empty-declared-group", "both declared groups must contain at least one sample")
    return sample_order, groups


def load_counts(
    rows: list[list[str]], sample_order: list[str]
) -> tuple[list[str], dict[str, dict[str, tuple[int, int]]]]:
    event_order: list[str] = []
    counts: dict[str, dict[str, tuple[int, int]]] = {}
    expected_samples = set(sample_order)

    for line_number, row in enumerate(rows, start=2):
        event_id = validate_label(row[0], "event_id", line_number)
        sample_id = validate_label(row[1], "sample_id", line_number)
        inclusion = parse_nonnegative_integer(row[2], "inclusion_count", line_number)
        exclusion = parse_nonnegative_integer(row[3], "exclusion_count", line_number)

        if event_id not in counts:
            event_order.append(event_id)
            counts[event_id] = {}
        if sample_id in counts[event_id]:
            raise UserError(
                "duplicate-event-sample",
                f"counts line {line_number} repeats one event-sample pair",
            )
        counts[event_id][sample_id] = (inclusion, exclusion)

    if not event_order:
        raise UserError("empty-counts", "counts input contains no event-sample rows")

    for event_id in event_order:
        observed_samples = set(counts[event_id])
        missing = expected_samples - observed_samples
        extra = observed_samples - expected_samples
        if missing or extra:
            raise UserError(
                "incomplete-event-sample-grid",
                f"event {event_id!r} does not have exactly one row for every declared sample "
                f"(missing={len(missing)}, extra={len(extra)})",
            )
    return event_order, counts


def fraction_fields(value: Fraction | None, stem: str) -> dict[str, Any]:
    if value is None:
        return {stem: None, f"{stem}_fraction": None}
    return {
        stem: round(value.numerator / value.denominator, 12),
        f"{stem}_fraction": f"{value.numerator}/{value.denominator}",
    }


def input_record(blob: InputBlob) -> dict[str, Any]:
    return {"name": blob.name, "bytes": len(blob.data), "sha256": blob.sha256}


def build_report(
    counts_blob: InputBlob,
    groups_blob: InputBlob,
    group_a: str,
    group_b: str,
    minimum_coverage: int,
) -> dict[str, Any]:
    if (counts_blob.device, counts_blob.inode) == (groups_blob.device, groups_blob.inode):
        raise UserError("inputs-alias", "counts and groups must be distinct files")

    group_a = validate_label(group_a, "group A")
    group_b = validate_label(group_b, "group B")
    group_rows = parse_tsv(groups_blob, GROUP_HEADERS)
    count_rows = parse_tsv(counts_blob, COUNT_HEADERS)
    sample_order, sample_groups = load_groups(group_rows, group_a, group_b)
    event_order, counts = load_counts(count_rows, sample_order)

    event_results: list[dict[str, Any]] = []
    estimable_pairs = 0
    estimable_deltas = 0

    for event_id in event_order:
        sample_results: list[dict[str, Any]] = []
        by_group: dict[str, list[Fraction]] = {group_a: [], group_b: []}
        for sample_id in sample_order:
            inclusion, exclusion = counts[event_id][sample_id]
            coverage = inclusion + exclusion
            group = sample_groups[sample_id]
            sample_result: dict[str, Any] = {
                "sample_id": sample_id,
                "group": group,
                "inclusion_count": inclusion,
                "exclusion_count": exclusion,
                "coverage": coverage,
            }
            if coverage < minimum_coverage:
                sample_result.update(
                    {
                        "status": "not-estimable",
                        "reason": "coverage-below-minimum",
                        **fraction_fields(None, "psi"),
                    }
                )
            else:
                psi = Fraction(inclusion, coverage)
                by_group[group].append(psi)
                estimable_pairs += 1
                sample_result.update(
                    {"status": "estimated", "reason": None, **fraction_fields(psi, "psi")}
                )
            sample_results.append(sample_result)

        group_results: list[dict[str, Any]] = []
        group_means: dict[str, Fraction | None] = {}
        for group in (group_a, group_b):
            values = by_group[group]
            mean = sum(values, Fraction(0, 1)) / len(values) if values else None
            group_means[group] = mean
            group_result: dict[str, Any] = {
                "group": group,
                "total_samples": sum(1 for value in sample_groups.values() if value == group),
                "estimable_samples": len(values),
                "status": "estimated" if mean is not None else "not-estimable",
                "reason": None if mean is not None else "no-samples-meet-minimum-coverage",
                **fraction_fields(mean, "mean_psi"),
            }
            group_results.append(group_result)

        if group_means[group_a] is None or group_means[group_b] is None:
            delta: Fraction | None = None
            delta_status = "not-estimable"
            delta_reason = "one-or-both-groups-have-no-estimable-samples"
        else:
            delta = group_means[group_b] - group_means[group_a]
            delta_status = "estimated"
            delta_reason = None
            estimable_deltas += 1

        event_results.append(
            {
                "event_id": event_id,
                "samples": sample_results,
                "groups": group_results,
                "delta": {
                    "contrast": f"{group_b} - {group_a}",
                    "status": delta_status,
                    "reason": delta_reason,
                    **fraction_fields(delta, "delta_psi"),
                },
            }
        )

    pair_count = len(event_order) * len(sample_order)
    group_sizes = {
        group_a: sum(1 for value in sample_groups.values() if value == group_a),
        group_b: sum(1 for value in sample_groups.values() if value == group_b),
    }
    return {
        "schema_version": "1.0.0",
        "status": "completed",
        "analysis": "junction-psi-and-declared-two-group-delta",
        "inputs": {
            "counts": input_record(counts_blob),
            "groups": input_record(groups_blob),
        },
        "declarations": {
            "group_a": group_a,
            "group_b": group_b,
            "minimum_coverage": minimum_coverage,
            "sample_psi": "inclusion_count / (inclusion_count + exclusion_count)",
            "group_mean": "unweighted arithmetic mean of estimable sample PSI values",
            "delta": "group B mean PSI - group A mean PSI",
        },
        "summary": {
            "events": len(event_order),
            "samples": len(sample_order),
            "group_sizes": group_sizes,
            "event_sample_pairs": pair_count,
            "estimable_event_sample_pairs": estimable_pairs,
            "not_estimable_event_sample_pairs": pair_count - estimable_pairs,
            "events_with_estimable_delta": estimable_deltas,
            "events_without_estimable_delta": len(event_order) - estimable_deltas,
        },
        "events": event_results,
        "interpretation_boundary": (
            "Descriptive prepared-count calculation only; no junction discovery, "
            "isoform inference, hypothesis testing, or biological or clinical conclusion."
        ),
    }


def report_bytes(
    report: dict[str, Any], max_bytes: int = MAX_REPORT_BYTES
) -> bytes:
    payload = bytearray()
    encoder = json.JSONEncoder(indent=2, sort_keys=True, ensure_ascii=False)
    for chunk in encoder.iterencode(report):
        encoded = chunk.encode("utf-8")
        if len(payload) + len(encoded) > max_bytes:
            raise UserError(
                "report-too-large",
                f"serialized report exceeds the {max_bytes}-byte limit",
                "needs-tool",
            )
        payload.extend(encoded)
    if len(payload) + 1 > max_bytes:
        raise UserError(
            "report-too-large",
            f"serialized report exceeds the {max_bytes}-byte limit",
            "needs-tool",
        )
    payload.extend(b"\n")
    return bytes(payload)


def open_output_parent(path_text: str) -> tuple[int, str]:
    raw = os.fspath(path_text)
    if not raw or "\x00" in raw:
        raise UserError(
            "invalid-output", "output path is empty or invalid", "invalid-output"
        )
    path = Path(raw).expanduser()
    if ".." in path.parts or path.name in {"", ".", ".."}:
        raise UserError(
            "invalid-output",
            "output path must name a file without parent traversal",
            "invalid-output",
        )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise UserError(
            "safe-publication-unavailable",
            "platform cannot pin an output parent without following symlinks",
            "needs-tool",
        )
    if path.is_absolute():
        anchor = Path(path.anchor)
        parts = path.parts[1:]
    else:
        anchor = Path.cwd()
        parts = path.parts
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow | directory
    descriptor = -1
    try:
        descriptor = os.open(anchor, flags)
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise UserError(
            "unsafe-output-parent",
            "output parent must exist and contain no symlink components",
            "invalid-output",
        ) from exc


def write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def unlink_owned(
    directory_descriptor: int, name: str, identity: tuple[int, int]
) -> bool:
    try:
        current = os.stat(
            name, dir_fd=directory_descriptor, follow_symlinks=False
        )
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_descriptor)
    return True


def publish_new_json(
    path_text: str,
    report: dict[str, Any],
    max_report_bytes: int = MAX_REPORT_BYTES,
) -> None:
    payload = report_bytes(report, max_report_bytes)
    directory_descriptor, leaf = open_output_parent(path_text)
    try:
        temporary_name = f".{leaf}.tmp-{secrets.token_hex(12)}"
    except BaseException:
        os.close(directory_descriptor)
        raise
    temporary_identity: tuple[int, int] | None = None
    temporary_created = False
    temporary_present = False
    final_present = False
    original_error: BaseException | None = None
    cleanup_failures: list[str] = []
    try:
        output_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = -1
        try:
            descriptor = os.open(
                temporary_name,
                output_flags,
                0o600,
                dir_fd=directory_descriptor,
            )
            temporary_created = True
            state = os.fstat(descriptor)
            temporary_identity = (state.st_dev, state.st_ino)
            temporary_present = True
            write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

        try:
            os.link(
                temporary_name,
                leaf,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise UserError(
                "output-exists",
                "output already exists; choose a new path",
                "invalid-output",
            ) from exc
        final_present = True
        final_state = os.stat(
            leaf, dir_fd=directory_descriptor, follow_symlinks=False
        )
        if (final_state.st_dev, final_state.st_ino) != temporary_identity:
            raise OSError("published output identity differs from staged data")

        if not unlink_owned(
            directory_descriptor, temporary_name, temporary_identity
        ):
            raise OSError("staged output identity changed before cleanup")
        temporary_present = False
        os.fsync(directory_descriptor)

        final_state = os.stat(
            leaf, dir_fd=directory_descriptor, follow_symlinks=False
        )
        if (final_state.st_dev, final_state.st_ino) != temporary_identity:
            raise OSError("published output identity changed before completion")
    except BaseException as exc:
        original_error = exc
    finally:
        if original_error is not None:
            if temporary_created and temporary_identity is None:
                cleanup_failures.append("staged:identity-unavailable")
            if final_present and temporary_identity is not None:
                try:
                    if not unlink_owned(
                        directory_descriptor, leaf, temporary_identity
                    ):
                        cleanup_failures.append("published:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(
                        f"published:{exc.__class__.__name__}"
                    )
            if temporary_present and temporary_identity is not None:
                try:
                    if not unlink_owned(
                        directory_descriptor,
                        temporary_name,
                        temporary_identity,
                    ):
                        cleanup_failures.append("staged:identity-changed")
                except OSError as exc:
                    cleanup_failures.append(f"staged:{exc.__class__.__name__}")
            if temporary_created:
                try:
                    os.fsync(directory_descriptor)
                except OSError as exc:
                    cleanup_failures.append(f"directory:{exc.__class__.__name__}")
        os.close(directory_descriptor)

    if cleanup_failures:
        raise UserError(
            "publication-rollback-failed",
            "output publication failed and owned files could not all be rolled back: "
            + ", ".join(cleanup_failures),
            "io-error",
        ) from original_error
    if original_error is not None:
        raise original_error


def self_test() -> int:
    counts_text = """event_id\tsample_id\tinclusion_count\texclusion_count
E1\tc1\t2\t8
E1\tc2\t4\t16
E1\tc3\t1\t3
E1\tt1\t6\t4
E1\tt2\t12\t8
E1\tt3\t0\t0
E2\tc1\t5\t5
E2\tc2\t10\t10
E2\tc3\t8\t8
E2\tt1\t3\t7
E2\tt2\t6\t14
E2\tt3\t9\t21
E3\tc1\t1\t1
E3\tc2\t2\t2
E3\tc3\t0\t0
E3\tt1\t9\t1
E3\tt2\t18\t2
E3\tt3\t27\t3
"""
    groups_text = """sample_id\tgroup
c1\tcontrol
c2\tcontrol
c3\tcontrol
t1\ttreated
t2\ttreated
t3\ttreated
"""

    with tempfile.TemporaryDirectory(prefix="junction-psi-self-test-") as temporary:
        root = Path(temporary).resolve()
        counts_path = root / "counts.tsv"
        groups_path = root / "groups.tsv"
        output_path = root / "report.json"
        parent_alias = root / "explicit-parent-alias"
        counts_path.write_text(counts_text, encoding="utf-8")
        groups_path.write_text(groups_text, encoding="utf-8")
        parent_alias.symlink_to(root, target_is_directory=True)

        counts_blob = read_regular_leaf(str(counts_path), "counts")
        groups_blob = read_regular_leaf(str(parent_alias / "groups.tsv"), "groups")
        report = build_report(counts_blob, groups_blob, "control", "treated", 10)

        assert report["summary"] == {
            "events": 3,
            "samples": 6,
            "group_sizes": {"control": 3, "treated": 3},
            "event_sample_pairs": 18,
            "estimable_event_sample_pairs": 13,
            "not_estimable_event_sample_pairs": 5,
            "events_with_estimable_delta": 2,
            "events_without_estimable_delta": 1,
        }
        assert report["events"][0]["delta"]["delta_psi_fraction"] == "2/5"
        assert report["events"][1]["delta"]["delta_psi_fraction"] == "-1/5"
        assert report["events"][2]["delta"]["status"] == "not-estimable"
        assert report["events"][2]["groups"][0]["mean_psi"] is None

        publish_new_json(str(output_path), report)
        original = output_path.read_bytes()
        assert json.loads(original)["status"] == "completed"
        try:
            publish_new_json(str(output_path), report)
        except UserError as exc:
            assert exc.code == "output-exists"
        else:
            raise AssertionError("existing output was not refused")
        assert output_path.read_bytes() == original

        linked_output = parent_alias / "linked-output.json"
        try:
            publish_new_json(str(linked_output), report)
        except UserError as exc:
            assert exc.code == "unsafe-output-parent"
        else:
            raise AssertionError("symlinked output parent was accepted")
        assert not (root / linked_output.name).exists()

        expected_payload = report_bytes(report)
        short_output = root / "short-write.json"
        original_write = os.write

        def short_write(descriptor: int, data: bytes) -> int:
            return original_write(descriptor, data[:7])

        os.write = short_write
        try:
            publish_new_json(str(short_output), report)
        finally:
            os.write = original_write
        assert short_output.read_bytes() == expected_payload

        zero_output = root / "zero-write.json"

        def zero_write(descriptor: int, data: bytes) -> int:
            return 0

        os.write = zero_write
        try:
            try:
                publish_new_json(str(zero_output), report)
            except OSError as exc:
                assert "made no progress" in str(exc)
            else:
                raise AssertionError("zero-byte write was accepted")
        finally:
            os.write = original_write
        assert not zero_output.exists()

        fsync_output = root / "post-link-fsync.json"
        original_fsync = os.fsync
        directory_fsync_failed = False

        def fail_first_directory_fsync(descriptor: int) -> None:
            nonlocal directory_fsync_failed
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not directory_fsync_failed:
                directory_fsync_failed = True
                raise OSError("injected post-link directory fsync failure")
            original_fsync(descriptor)

        os.fsync = fail_first_directory_fsync
        try:
            try:
                publish_new_json(str(fsync_output), report)
            except OSError as exc:
                assert "directory fsync failure" in str(exc)
            else:
                raise AssertionError("post-link fsync failure was ignored")
        finally:
            os.fsync = original_fsync
        assert directory_fsync_failed and not fsync_output.exists()

        unlink_output = root / "unlink-failure.json"
        original_unlink = os.unlink

        def fail_staged_unlink(
            path: str | bytes, *args: Any, **kwargs: Any
        ) -> None:
            if os.fspath(path).startswith(f".{unlink_output.name}.tmp-"):
                raise PermissionError("injected staged unlink failure")
            original_unlink(path, *args, **kwargs)

        os.unlink = fail_staged_unlink
        try:
            try:
                publish_new_json(str(unlink_output), report)
            except UserError as exc:
                assert (
                    exc.code == "publication-rollback-failed"
                    and exc.status == "io-error"
                )
            else:
                raise AssertionError("rollback unlink failure was hidden")
        finally:
            os.unlink = original_unlink
        assert not unlink_output.exists()
        staged_leftovers = list(root.glob(f".{unlink_output.name}.tmp-*"))
        assert len(staged_leftovers) == 1
        staged_leftovers[0].unlink()

        counts_link = root / "counts-link.tsv"
        counts_link.symlink_to(counts_path)
        try:
            read_regular_leaf(str(counts_link), "counts")
        except UserError as exc:
            assert exc.code in {"input-leaf-symlink", "input-open-failed"}
        else:
            raise AssertionError("input leaf symlink was not refused")

        counts_fifo = root / "counts.fifo"
        os.mkfifo(counts_fifo)
        try:
            read_regular_leaf(str(counts_fifo), "counts")
        except UserError as exc:
            assert exc.code == "input-not-regular"
        else:
            raise AssertionError("FIFO input was not refused")

        try:
            validate_label("x" * (MAX_LABEL_CHARS + 1), "event_id", 2)
        except UserError as exc:
            assert exc.code == "invalid-label" and exc.status == "invalid-input"
        else:
            raise AssertionError("oversized label was accepted")

        oversized_output = root / "oversized-report.json"
        try:
            publish_new_json(str(oversized_output), report, max_report_bytes=1)
        except UserError as exc:
            assert exc.code == "report-too-large" and exc.status == "needs-tool"
        else:
            raise AssertionError("oversized report was published")
        assert not oversized_output.exists()
        assert not list(root.glob(".*.tmp-*"))

    print(
        json.dumps(
            {
                "status": "pass",
                "version": "0.7.0",
                "events": 3,
                "samples": 6,
                "event_sample_pairs": 18,
                "estimable_event_sample_pairs": 13,
            },
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate descriptive PSI and a declared two-group delta from prepared junction counts."
    )
    parser.add_argument("--counts", help="prepared long-form inclusion/exclusion count TSV")
    parser.add_argument("--groups", help="exact sample-to-group TSV")
    parser.add_argument("--group-a", help="baseline group label")
    parser.add_argument("--group-b", help="comparison group label; delta is B minus A")
    parser.add_argument("--min-coverage", help="minimum inclusion plus exclusion count")
    parser.add_argument("--output", help="new JSON report path")
    parser.add_argument("--self-test", action="store_true", help="run the deterministic built-in self-test")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()

    required = {
        "--counts": args.counts,
        "--groups": args.groups,
        "--group-a": args.group_a,
        "--group-b": args.group_b,
        "--min-coverage": args.min_coverage,
        "--output": args.output,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        print(f"error [missing-arguments]: required arguments: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        minimum_coverage = parse_minimum_coverage(args.min_coverage)
        counts_blob = read_regular_leaf(args.counts, "counts")
        groups_blob = read_regular_leaf(args.groups, "groups")
        report = build_report(
            counts_blob,
            groups_blob,
            args.group_a,
            args.group_b,
            minimum_coverage,
        )
        publish_new_json(args.output, report)
    except UserError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 3 if exc.status in {"needs-tool", "io-error"} else 2
    except OSError as exc:
        print(f"error [publication-io-failed]: {exc}", file=sys.stderr)
        return 3

    print(json.dumps({"status": "completed", "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
