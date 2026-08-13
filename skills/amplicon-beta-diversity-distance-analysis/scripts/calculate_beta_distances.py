#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Calculate bounded pairwise beta-diversity distances from an integer TSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


VERSION = "0.8.0"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_FEATURES = 50_000
MAX_SAMPLES = 2_000
MAX_CELLS = 2_000_000
MAX_PAIRS = 20_000
MAX_PAIR_FEATURE_COMPARISONS = 20_000_000
MAX_ID_CHARS = 256
MAX_COUNT_CHARS = 16
MAX_SAFE_INTEGER = 9_007_199_254_740_991
ASCII_INTEGER = re.compile(r"[0-9]+\Z")


class InputError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("input validation failed")
        self.issues = issues


def issue(
    code: str,
    *,
    line: int | None = None,
    field: str | None = None,
    value: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "role": "feature-table"}
    if line is not None:
        result["line"] = line
    if field is not None:
        result["field"] = field
    if value is not None:
        result["value"] = value
    return result


def validate_id(value: str, *, line: int, field: str) -> None:
    if not value:
        raise InputError([issue("empty-id", line=line, field=field)])
    if value != value.strip():
        raise InputError([issue(
            "surrounding-whitespace", line=line, field=field
        )])
    if len(value) > MAX_ID_CHARS:
        raise InputError([issue("id-too-long", line=line, field=field)])
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InputError([issue("control-character", line=line, field=field)])


def read_local_file(path: Path, *, root: Path | None = None) -> tuple[bytes, str]:
    supplied = Path(path)
    if ".." in supplied.parts:
        raise InputError([issue("parent-traversal")])
    lexical_root = Path(os.path.abspath(Path.cwd() if root is None else root))
    parent_fd = -1
    try:
        root_state = os.lstat(lexical_root)
        if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
            raise InputError([issue("unsafe-working-directory")])
        candidate = Path(os.path.abspath(
            supplied if supplied.is_absolute() else lexical_root / supplied
        ))
        try:
            relative = candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise InputError([issue("path-outside-working-directory")]) from exc
        if not relative.parts:
            raise InputError([issue("input-not-regular-file")])

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
            raise InputError([issue("unsafe-working-directory")])
        for part in relative.parts[:-1]:
            try:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise InputError([issue("input-parent-symlink")]) from exc
            os.close(parent_fd)
            parent_fd = child_fd

        name = relative.parts[-1]
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise InputError([issue("input-not-regular-file")])
        if before.st_size > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large")])
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise InputError([issue("input-not-regular-file")])
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise InputError([issue("input-changed-during-read")])
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read(MAX_INPUT_BYTES + 1)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise InputError([issue("input-too-large")])
        if any(
            getattr(opened, field) != getattr(after_open, field)
            for field in stable_fields
        ):
            raise InputError([issue("input-changed-during-read")])
        if any(
            getattr(after_open, field) != getattr(after_path, field)
            for field in stable_fields
        ):
            raise InputError([issue("input-changed-during-read")])
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError([issue("input-not-utf8")]) from exc
        if "\x00" in text:
            raise InputError([issue("nul-byte-in-input")])
        return payload, text
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise InputError([issue("input-unreadable")]) from exc
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def parse_count(raw: str, *, line: int, sample_id: str) -> int:
    if not raw or len(raw) > MAX_COUNT_CHARS or not ASCII_INTEGER.fullmatch(raw):
        raise InputError([issue(
            "invalid-count", line=line, field=sample_id, value=raw
        )])
    value = int(raw)
    if value > MAX_SAFE_INTEGER:
        raise InputError([issue(
            "count-too-large", line=line, field=sample_id, value=raw
        )])
    return value


def parse_feature_table(text: str) -> dict[str, Any]:
    try:
        reader = csv.reader(io.StringIO(text), delimiter="\t", strict=True)
        header = next(reader)
    except StopIteration as exc:
        raise InputError([issue("missing-header")]) from exc
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv")]) from exc

    if not header or header[0] != "feature_id":
        raise InputError([issue(
            "ambiguous-table-orientation",
            value="first-header-must-be-feature_id",
        )])
    if len(header) < 3:
        raise InputError([issue("fewer-than-two-samples")])
    if len(header) != len(set(header)):
        raise InputError([issue("duplicate-header")])
    sample_ids = header[1:]
    if len(sample_ids) > MAX_SAMPLES:
        raise InputError([issue("too-many-samples", value=len(sample_ids))])
    for sample_id in sample_ids:
        validate_id(sample_id, line=1, field="sample_id")
    pair_count = len(sample_ids) * (len(sample_ids) - 1) // 2
    if pair_count > MAX_PAIRS:
        raise InputError([issue("too-many-sample-pairs", value=pair_count)])

    columns = {sample_id: [] for sample_id in sample_ids}
    feature_ids: set[str] = set()
    try:
        for row_number, row in enumerate(reader, start=1):
            line = row_number + 1
            if row_number > MAX_FEATURES:
                raise InputError([issue("too-many-features", line=line)])
            if row_number * len(sample_ids) > MAX_CELLS:
                raise InputError([issue(
                    "too-many-count-cells",
                    line=line,
                    value=row_number * len(sample_ids),
                )])
            if len(row) != len(header):
                raise InputError([issue("ragged-row", line=line)])
            feature_id = row[0]
            validate_id(feature_id, line=line, field="feature_id")
            if feature_id in feature_ids:
                raise InputError([issue(
                    "duplicate-feature-id",
                    line=line,
                    field="feature_id",
                    value=feature_id,
                )])
            feature_ids.add(feature_id)
            for sample_id, raw in zip(sample_ids, row[1:]):
                columns[sample_id].append(
                    parse_count(raw, line=line, sample_id=sample_id)
                )
    except csv.Error as exc:
        raise InputError([issue("malformed-tsv")]) from exc
    if not feature_ids:
        raise InputError([issue("no-feature-rows")])
    pair_feature_comparisons = pair_count * len(feature_ids)
    if pair_feature_comparisons > MAX_PAIR_FEATURE_COMPARISONS:
        raise InputError([issue(
            "too-many-pair-feature-comparisons",
            value=pair_feature_comparisons,
        )])
    for sample_id in sample_ids:
        if sum(columns[sample_id]) > MAX_SAFE_INTEGER:
            raise InputError([issue("sample-depth-too-large", field=sample_id)])
    return {
        "counts": columns,
        "feature_count": len(feature_ids),
        "pair_count": pair_count,
        "pair_feature_comparisons": pair_feature_comparisons,
        "sample_ids": sample_ids,
    }


def estimated_ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "denominator": denominator,
        "numerator": numerator,
        "status": "estimated",
        "value": numerator / denominator,
    }


def unavailable_ratio() -> dict[str, Any]:
    return {
        "denominator": None,
        "numerator": None,
        "reason": "zero-depth-sample",
        "status": "not-estimable",
        "value": None,
    }


def calculate_pair(
    sample_a: str,
    counts_a: list[int],
    sample_b: str,
    counts_b: list[int],
) -> dict[str, Any]:
    depth_a = sum(counts_a)
    depth_b = sum(counts_b)
    zero_depth = [
        sample_id
        for sample_id, depth in ((sample_a, depth_a), (sample_b, depth_b))
        if depth == 0
    ]
    if zero_depth:
        bray_curtis = unavailable_ratio()
        jaccard = unavailable_ratio()
    else:
        bray_numerator = sum(
            abs(count_a - count_b)
            for count_a, count_b in zip(counts_a, counts_b)
        )
        intersection = sum(
            count_a > 0 and count_b > 0
            for count_a, count_b in zip(counts_a, counts_b)
        )
        union = sum(
            count_a > 0 or count_b > 0
            for count_a, count_b in zip(counts_a, counts_b)
        )
        bray_curtis = estimated_ratio(bray_numerator, depth_a + depth_b)
        jaccard = estimated_ratio(union - intersection, union)
    return {
        "bray_curtis": bray_curtis,
        "jaccard_presence_absence": jaccard,
        "sample_a": sample_a,
        "sample_a_depth": depth_a,
        "sample_b": sample_b,
        "sample_b_depth": depth_b,
        "zero_depth_sample_ids": zero_depth,
    }


def analyze(payload: bytes, text: str) -> dict[str, Any]:
    parsed = parse_feature_table(text)
    sample_ids = sorted(parsed["sample_ids"])
    sample_depths = [
        {
            "depth": sum(parsed["counts"][sample_id]),
            "sample_id": sample_id,
        }
        for sample_id in sample_ids
    ]
    pairs = [
        calculate_pair(
            sample_a,
            parsed["counts"][sample_a],
            sample_b,
            parsed["counts"][sample_b],
        )
        for sample_a, sample_b in itertools.combinations(sample_ids, 2)
    ]
    return {
        "analysis": {
            "bray_curtis": "sum-absolute-differences-over-sum-counts",
            "group_comparison_performed": False,
            "jaccard_presence_absence": "one-minus-intersection-over-union",
            "method": "pairwise-descriptive-beta-diversity-distances",
            "ordination_performed": False,
            "rarefaction_or_normalization_performed": False,
        },
        "input": {
            "bytes": len(payload),
            "count_cell_count": (
                parsed["feature_count"] * len(parsed["sample_ids"])
            ),
            "feature_count": parsed["feature_count"],
            "orientation": "feature-rows-by-sample-columns",
            "sample_count": len(parsed["sample_ids"]),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "limitations": [
            "Feature identity, count semantics, sequencing adequacy, and cross-sample comparability are not independently verified.",
            "Distances describe only the supplied unmodified integer count table.",
            "No rarefaction, normalization, transformation, ordination, PERMANOVA or other group comparison, differential abundance, taxonomy, contamination, pathogen, biological, or clinical analysis was performed.",
        ],
        "pair_count": parsed["pair_count"],
        "pair_feature_comparisons": parsed["pair_feature_comparisons"],
        "pairs": pairs,
        "sample_depths": sample_depths,
        "sample_ids": sample_ids,
        "schema_version": "1.0",
        "zero_depth_sample_ids": [
            item["sample_id"] for item in sample_depths if item["depth"] == 0
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
    candidate = Path(os.path.abspath(
        path if path.is_absolute() else lexical_root / path
    ))
    try:
        relative = candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise PermissionError(
            f"output is outside the allowed root: {candidate}"
        ) from exc
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
    descriptor = -1
    identity: tuple[int, int] | None = None
    published = False
    cleanup_failures: list[str] = []
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline="", closefd=False
        ) as handle:
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
        final_state = os.stat(
            target_name, dir_fd=directory_fd, follow_symlinks=False
        )
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
                    "staged output cleanup failed: "
                    f"{cleanup_exc.__class__.__name__}"
                )
            try:
                os.fsync(directory_fd)
            except OSError as cleanup_exc:
                cleanup_failures.append(
                    "directory rollback sync failed: "
                    f"{cleanup_exc.__class__.__name__}"
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

    table = (
        "feature_id\tZ\tC\tB\tA\n"
        "f1\t0\t0\t1\t1\n"
        "f2\t0\t2\t0\t1\n"
        "f3\t0\t0\t0\t0\n"
        "f4\t0\t0\t0\t0\n"
    )
    report = analyze(table.encode(), table)
    check(report["input"]["feature_count"] == 4, "feature count differs")
    check(report["sample_ids"] == ["A", "B", "C", "Z"],
          "sample order differs")
    check(report["pair_count"] == 6, "pair count differs")
    check(
        [(pair["sample_a"], pair["sample_b"]) for pair in report["pairs"]]
        == [("A", "B"), ("A", "C"), ("A", "Z"),
            ("B", "C"), ("B", "Z"), ("C", "Z")],
        "upper-triangle order differs",
    )
    pairs = {
        (pair["sample_a"], pair["sample_b"]): pair
        for pair in report["pairs"]
    }
    check(pairs[("A", "B")]["bray_curtis"] == {
        "denominator": 3,
        "numerator": 1,
        "status": "estimated",
        "value": 1 / 3,
    }, "A-B Bray-Curtis differs")
    check(pairs[("A", "B")]["jaccard_presence_absence"] == {
        "denominator": 2,
        "numerator": 1,
        "status": "estimated",
        "value": 1 / 2,
    }, "A-B Jaccard differs")
    check(pairs[("A", "C")]["bray_curtis"]["numerator"] == 2 and
          pairs[("A", "C")]["bray_curtis"]["denominator"] == 4,
          "A-C Bray-Curtis ratio differs")
    check(pairs[("A", "C")]["jaccard_presence_absence"]["numerator"] == 1 and
          pairs[("A", "C")]["jaccard_presence_absence"]["denominator"] == 2,
          "A-C Jaccard ratio differs")
    check(pairs[("B", "C")]["bray_curtis"]["numerator"] == 3 and
          pairs[("B", "C")]["bray_curtis"]["denominator"] == 3,
          "B-C Bray-Curtis ratio differs")
    check(pairs[("B", "C")]["jaccard_presence_absence"]["numerator"] == 2 and
          pairs[("B", "C")]["jaccard_presence_absence"]["denominator"] == 2,
          "B-C Jaccard ratio differs")
    for pair_id in (("A", "Z"), ("B", "Z"), ("C", "Z")):
        pair = pairs[pair_id]
        check(pair["bray_curtis"] == {
            "denominator": None,
            "numerator": None,
            "reason": "zero-depth-sample",
            "status": "not-estimable",
            "value": None,
        }, f"{pair_id} Bray-Curtis zero-depth status differs")
        check(pair["jaccard_presence_absence"]["status"] == "not-estimable" and
              pair["jaccard_presence_absence"]["reason"] == "zero-depth-sample",
              f"{pair_id} Jaccard zero-depth status differs")
    check(report["zero_depth_sample_ids"] == ["Z"],
          "zero-depth sample IDs differ")
    check(
        json.dumps(report, allow_nan=False, sort_keys=True)
        == json.dumps(analyze(table.encode(), table), allow_nan=False, sort_keys=True),
        "repeat analysis differs",
    )

    identical = "feature_id\tB\tA\nf1\t2\t2\nf2\t0\t0\n"
    identical_pair = analyze(identical.encode(), identical)["pairs"][0]
    check(identical_pair["bray_curtis"]["value"] == 0.0,
          "identical Bray-Curtis differs")
    check(identical_pair["jaccard_presence_absence"]["value"] == 0.0,
          "identical Jaccard differs")

    expect_issue("missing-header", lambda: parse_feature_table(""))
    expect_issue(
        "ambiguous-table-orientation",
        lambda: parse_feature_table("sample_id\tA\tB\nf1\t1\t2\n"),
    )
    expect_issue(
        "fewer-than-two-samples",
        lambda: parse_feature_table("feature_id\tA\nf1\t1\n"),
    )
    expect_issue(
        "duplicate-header",
        lambda: parse_feature_table("feature_id\tA\tA\nf1\t1\t2\n"),
    )
    expect_issue(
        "duplicate-feature-id",
        lambda: parse_feature_table(
            "feature_id\tA\tB\nf1\t1\t2\nf1\t0\t1\n"
        ),
    )
    expect_issue(
        "invalid-count",
        lambda: parse_feature_table("feature_id\tA\tB\nf1\t-1\t2\n"),
    )
    expect_issue(
        "invalid-count",
        lambda: parse_feature_table("feature_id\tA\tB\nf1\t1.0\t2\n"),
    )
    expect_issue(
        "invalid-count",
        lambda: parse_feature_table("feature_id\tA\tB\nf1\t1e2\t2\n"),
    )
    expect_issue(
        "ragged-row",
        lambda: parse_feature_table("feature_id\tA\tB\nf1\t1\n"),
    )
    expect_issue(
        "no-feature-rows",
        lambda: parse_feature_table("feature_id\tA\tB\n"),
    )
    expect_issue(
        "count-too-large",
        lambda: parse_feature_table(
            f"feature_id\tA\tB\nf1\t{MAX_SAFE_INTEGER + 1}\t0\n"
        ),
    )
    expect_issue(
        "sample-depth-too-large",
        lambda: parse_feature_table(
            "feature_id\tA\tB\n"
            f"f1\t{MAX_SAFE_INTEGER}\t0\n"
            "f2\t1\t0\n"
        ),
    )
    crowded_ids = [f"S{index:03d}" for index in range(202)]
    crowded = (
        "feature_id\t" + "\t".join(crowded_ids) + "\n"
        + "f1\t" + "\t".join("0" for _ in crowded_ids) + "\n"
    )
    expect_issue("too-many-sample-pairs", lambda: parse_feature_table(crowded))

    global MAX_PAIR_FEATURE_COMPARISONS
    original_pair_feature_cap = MAX_PAIR_FEATURE_COMPARISONS
    MAX_PAIR_FEATURE_COMPARISONS = 2
    try:
        expect_issue(
            "too-many-pair-feature-comparisons",
            lambda: parse_feature_table(
                "feature_id\tA\tB\tC\nf1\t1\t1\t1\n"
            ),
        )
    finally:
        MAX_PAIR_FEATURE_COMPARISONS = original_pair_feature_cap

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "root"
        root.mkdir()
        input_path = root / "counts.tsv"
        input_path.write_text(table, encoding="utf-8")
        payload, loaded = read_local_file(input_path, root=root)
        check(payload == table.encode() and loaded == table, "safe read differs")

        linked_input = root / "linked-counts.tsv"
        linked_input.symlink_to(input_path)
        expect_issue(
            "input-not-regular-file",
            lambda: read_local_file(linked_input, root=root),
        )
        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "counts.tsv").write_text(table, encoding="utf-8")
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect_issue(
            "input-parent-symlink",
            lambda: read_local_file(
                linked_input_parent / "counts.tsv", root=root
            ),
        )
        expect_issue(
            "parent-traversal",
            lambda: read_local_file(Path("..") / "counts.tsv", root=root),
        )
        expect_issue(
            "path-outside-working-directory",
            lambda: read_local_file(Path(temporary) / "outside.tsv", root=root),
        )

        output = root / "report.json"
        write_new(output, "{}\n", root=root)
        check(output.read_text(encoding="utf-8") == "{}\n", "write differs")
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

        real_output_parent = root / "real-output-parent"
        real_output_parent.mkdir()
        linked_output_parent = root / "linked-output-parent"
        linked_output_parent.symlink_to(real_output_parent, target_is_directory=True)
        try:
            write_new(Path("linked-output-parent") / "report.json", "{}\n",
                      root=root)
        except PermissionError:
            checks += 1
        else:
            raise AssertionError("symlinked output parent was accepted")

        existing_target = root / "existing-target.json"
        existing_target.write_text("sentinel\n", encoding="utf-8")
        output_link = root / "output-link.json"
        output_link.symlink_to(existing_target)
        try:
            write_new(output_link, "replacement\n", root=root)
        except FileExistsError:
            check(existing_target.read_text(encoding="utf-8") == "sentinel\n",
                  "output symlink target changed")
        else:
            raise AssertionError("output symlink was accepted")

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
    result.add_argument("--feature-table", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    if arguments.feature_table is None or arguments.output is None:
        parser().error("--feature-table and --output are required for execution")
    try:
        payload, text = read_local_file(arguments.feature_table)
        report = analyze(payload, text)
        rendered = json.dumps(
            report, allow_nan=False, indent=2, sort_keys=True
        ) + "\n"
        write_new(arguments.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "features": report["input"]["feature_count"],
            "output": str(arguments.output),
            "pairs": report["pair_count"],
            "samples": report["input"]["sample_count"],
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
