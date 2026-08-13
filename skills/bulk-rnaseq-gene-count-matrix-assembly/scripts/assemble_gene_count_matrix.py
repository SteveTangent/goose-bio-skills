#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble matched single-sample gene-count JSON reports into one matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


VERSION = "0.9.0"
MAX_INPUT_BYTES = 64 * 1024 * 1024
MIN_SAMPLES = 2
MAX_SAMPLES = 128
MAX_GENES = 100_000
MAX_CELLS = 5_000_000
MAX_ID_CHARS = 256
MAX_SAFE_INTEGER = 9_007_199_254_740_991
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GENE_KEYS = {"contig", "count", "exon_count", "gene_id", "strand"}
CONTRACT_KEYS = {
    "duplicate_primary_records",
    "feature",
    "identity",
    "minimum_mapq",
    "missing_nh",
    "nh_greater_than_one",
    "secondary_and_supplementary",
    "strandedness",
}


class ContractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def reject(code: str, message: str) -> ContractError:
    return ContractError(code, message)


def validate_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise reject("invalid-id", f"{field} must be a nonempty trimmed string")
    if len(value) > MAX_ID_CHARS:
        raise reject("invalid-id", f"{field} exceeds the identifier limit")
    if any(
        ord(character) < 32
        or ord(character) == 127
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise reject("invalid-id", f"{field} contains a control character")
    return value


def bounded_integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_SAFE_INTEGER,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise reject("invalid-integer", f"{field} must be a JSON integer")
    if value < minimum or value > maximum:
        raise reject("integer-out-of-range", f"{field} is outside the accepted range")
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise reject("duplicate-json-key", "a JSON object contains a duplicate key")
        result[key] = value
    return result


def parse_json(text: str) -> dict[str, Any]:
    def invalid_constant(_: str) -> None:
        raise reject("invalid-json-number", "non-finite JSON numbers are forbidden")

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise reject("invalid-json", "input is not bounded valid JSON") from exc
    if not isinstance(value, dict):
        raise reject("invalid-report", "the source report must be one JSON object")
    return value


def _path_parts(path: Path, root: Path, role: str) -> tuple[Path, tuple[str, ...], os.stat_result]:
    supplied = Path(path)
    if ".." in supplied.parts:
        raise reject(f"{role}-parent-traversal", f"{role} path contains parent traversal")
    lexical_root = Path(os.path.abspath(root))
    root_state = os.lstat(lexical_root)
    if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
        raise reject("unsafe-working-directory", "working directory is not a regular directory")
    candidate = Path(os.path.abspath(
        supplied if supplied.is_absolute() else lexical_root / supplied
    ))
    try:
        relative = candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise reject(f"{role}-outside-working-directory", f"{role} path is outside the working directory") from exc
    if not relative.parts:
        raise reject(f"invalid-{role}-path", f"{role} path names the working directory")
    return candidate, relative.parts, root_state


def _open_parent(path: Path, root: Path, role: str) -> tuple[Path, int, str]:
    candidate, parts, root_state = _path_parts(path, root, role)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(Path(os.path.abspath(root)), flags)
    opened_root = os.fstat(descriptor)
    if (opened_root.st_dev, opened_root.st_ino) != (
        root_state.st_dev,
        root_state.st_ino,
    ):
        os.close(descriptor)
        raise reject("unsafe-working-directory", "working directory identity changed")
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as exc:
                raise reject(f"unsafe-{role}-parent", f"{role} parent is absent or unsafe") from exc
            os.close(descriptor)
            descriptor = child
        return candidate, descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def read_input(path: Path, *, root: Path | None = None) -> tuple[bytes, str]:
    lexical_root = Path.cwd() if root is None else root
    parent_fd = -1
    try:
        _, parent_fd, name = _open_parent(path, lexical_root, "input")
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise reject("input-not-regular-file", "input must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise reject("input-too-large", "input exceeds the byte limit")
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
                raise reject("input-not-regular-file", "input must be a regular file")
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise reject("input-changed-during-read", "input identity changed before reading")
            chunks: list[bytes] = []
            total = 0
            while total <= MAX_INPUT_BYTES:
                chunk = os.read(descriptor, min(1024 * 1024, MAX_INPUT_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            payload = b"".join(chunks)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_INPUT_BYTES:
            raise reject("input-too-large", "input exceeds the byte limit")
        if any(getattr(opened, key) != getattr(after_open, key) for key in stable):
            raise reject("input-changed-during-read", "input changed while being read")
        if any(getattr(after_open, key) != getattr(after_path, key) for key in stable):
            raise reject("input-changed-during-read", "input path changed while being read")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise reject("input-not-utf8", "input is not UTF-8") from exc
        if "\x00" in text:
            raise reject("nul-byte-in-input", "input contains a NUL byte")
        return payload, text
    except ContractError:
        raise
    except (OSError, ValueError) as exc:
        raise reject("input-unreadable", "input cannot be read safely") from exc
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def validate_assignment_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != CONTRACT_KEYS:
        raise reject("invalid-assignment-contract", "assignment_contract has an unexpected schema")
    if value["feature"] != "exon" or value["identity"] != "gene_id":
        raise reject("invalid-assignment-contract", "assignment identity is not gene_id exon counting")
    if value["duplicate_primary_records"] != "duplicate-flag-alone-does-not-exclude; observed-count-reported":
        raise reject("invalid-assignment-contract", "duplicate-record policy is unsupported")
    if value["missing_nh"] != "accepted-by-mapq-and-reported":
        raise reject("invalid-assignment-contract", "missing-NH policy is unsupported")
    if value["nh_greater_than_one"] != "unassigned-multimapped":
        raise reject("invalid-assignment-contract", "multimapper policy is unsupported")
    if value["secondary_and_supplementary"] != "ignored-and-reported":
        raise reject("invalid-assignment-contract", "secondary-record policy is unsupported")
    if value["strandedness"] not in {"unstranded", "forward", "reverse"}:
        raise reject("invalid-assignment-contract", "strandedness is unsupported")
    bounded_integer(value["minimum_mapq"], "minimum_mapq", maximum=255)
    return deepcopy(value)


def validate_source(payload: bytes, report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "1.0":
        raise reject("unsupported-source-schema", "source schema_version must be 1.0")
    if report.get("status") != "completed" or report.get("analysis_performed") is not True:
        raise reject("source-not-completed", "source report must be completed")
    adapter = report.get("adapter")
    if not isinstance(adapter, dict) or adapter.get("name") != "count_gene_alignments":
        raise reject("unsupported-source-adapter", "source adapter must be count_gene_alignments")
    adapter_version = validate_id(adapter.get("version"), "adapter.version")
    sample_id = validate_id(report.get("sample_id"), "sample_id")

    inputs = report.get("inputs")
    gtf = inputs.get("gtf") if isinstance(inputs, dict) else None
    if not isinstance(gtf, dict) or not isinstance(gtf.get("sha256"), str):
        raise reject("missing-gtf-fingerprint", "source GTF SHA-256 is missing")
    gtf_sha256 = gtf["sha256"]
    if not SHA256.fullmatch(gtf_sha256):
        raise reject("invalid-gtf-fingerprint", "source GTF SHA-256 is invalid")

    assignment_contract = validate_assignment_contract(report.get("assignment_contract"))
    rows = report.get("counts")
    if not isinstance(rows, list) or not rows:
        raise reject("missing-gene-rows", "source report has no gene rows")
    if len(rows) > MAX_GENES:
        raise reject("too-many-genes", "source report exceeds the gene limit")

    genes: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != GENE_KEYS:
            raise reject("invalid-gene-row", "a gene row has an unexpected schema")
        gene_id = validate_id(row.get("gene_id"), "gene_id")
        if gene_id in genes:
            raise reject("duplicate-gene-id", "a source report repeats a gene_id")
        contig = validate_id(row.get("contig"), "contig")
        strand = row.get("strand")
        if strand not in {"+", "-"}:
            raise reject("invalid-gene-strand", "gene strand must be + or -")
        exon_count = bounded_integer(row.get("exon_count"), "exon_count", minimum=1)
        count = bounded_integer(row.get("count"), "count")
        genes[gene_id] = {
            "contig": contig,
            "count": count,
            "exon_count": exon_count,
            "gene_id": gene_id,
            "strand": strand,
        }

    gene_count = bounded_integer(gtf.get("gene_count"), "inputs.gtf.gene_count", minimum=1, maximum=MAX_GENES)
    exon_total = bounded_integer(gtf.get("exon_count"), "inputs.gtf.exon_count", minimum=1)
    if gene_count != len(genes) or exon_total != sum(row["exon_count"] for row in genes.values()):
        raise reject("inconsistent-gtf-summary", "source GTF summary does not match its gene rows")

    return {
        "adapter_version": adapter_version,
        "assignment_contract": assignment_contract,
        "bytes": len(payload),
        "genes": genes,
        "gtf_sha256": gtf_sha256,
        "sample_id": sample_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def load_source(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    payload, text = read_input(path, root=root)
    return validate_source(payload, parse_json(text))


def load_sources(
    paths: list[Path],
    loader: Callable[[Path], dict[str, Any]] = load_source,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    sample_count = len(paths)
    for path in paths:
        source = loader(path)
        if len(source["genes"]) * sample_count > MAX_CELLS:
            raise reject("too-many-count-cells", "matrix exceeds the count-cell limit")
        sources.append(source)
    return sources


def assemble(sources: list[dict[str, Any]]) -> dict[str, Any]:
    if len(sources) < MIN_SAMPLES:
        raise reject("too-few-samples", "at least two source reports are required")
    if len(sources) > MAX_SAMPLES:
        raise reject("too-many-samples", "source reports exceed the sample limit")
    ordered = sorted(sources, key=lambda source: source["sample_id"])
    sample_ids = [source["sample_id"] for source in ordered]
    if len(sample_ids) != len(set(sample_ids)):
        raise reject("duplicate-sample-id", "source reports repeat a sample_id")

    reference = ordered[0]
    gene_ids = sorted(reference["genes"])
    if len(gene_ids) * len(ordered) > MAX_CELLS:
        raise reject("too-many-count-cells", "matrix exceeds the count-cell limit")
    reference_tuples = {
        gene_id: (
            reference["genes"][gene_id]["contig"],
            reference["genes"][gene_id]["strand"],
            reference["genes"][gene_id]["exon_count"],
        )
        for gene_id in gene_ids
    }
    for source in ordered[1:]:
        if source["gtf_sha256"] != reference["gtf_sha256"]:
            raise reject("gtf-fingerprint-mismatch", "source reports use different GTF fingerprints")
        if source["assignment_contract"] != reference["assignment_contract"]:
            raise reject("assignment-contract-mismatch", "source reports use different assignment contracts")
        if set(source["genes"]) != set(reference["genes"]):
            raise reject("gene-set-mismatch", "source reports contain different gene sets")
        for gene_id in gene_ids:
            row = source["genes"][gene_id]
            if (row["contig"], row["strand"], row["exon_count"]) != reference_tuples[gene_id]:
                raise reject("gene-tuple-mismatch", "source reports disagree on a gene tuple")

    genes = [
        {
            "contig": reference["genes"][gene_id]["contig"],
            "counts": [source["genes"][gene_id]["count"] for source in ordered],
            "exon_count": reference["genes"][gene_id]["exon_count"],
            "gene_id": gene_id,
            "strand": reference["genes"][gene_id]["strand"],
        }
        for gene_id in gene_ids
    ]
    return {
        "adapter": {"name": "assemble_gene_count_matrix", "version": VERSION},
        "assembly_performed": True,
        "assignment_contract": deepcopy(reference["assignment_contract"]),
        "limits": {
            "maximum_count": MAX_SAFE_INTEGER,
            "maximum_count_cells": MAX_CELLS,
            "maximum_genes": MAX_GENES,
            "maximum_samples": MAX_SAMPLES,
        },
        "limitations": [
            "This is a structural join of completed raw gene-count reports, not independent validation of their SAM, GTF, sample, protocol, or cohort semantics.",
            "The upstream schema exposes a GTF fingerprint and gene tuples but not its full reference dictionary; full reference identity remains a researcher review boundary.",
            "No gene completion, filtering, normalization, transformation, batch correction, differential expression, biological interpretation, or clinical analysis was performed.",
        ],
        "matrix": {
            "count_cell_count": len(gene_ids) * len(ordered),
            "gene_count": len(gene_ids),
            "genes": genes,
            "orientation": "gene-rows-by-sample-order",
            "sample_count": len(ordered),
            "sample_ids": sample_ids,
        },
        "reference": {
            "gene_count": len(gene_ids),
            "gtf_sha256": reference["gtf_sha256"],
        },
        "schema_version": "1.0",
        "sources": [
            {
                "adapter": {
                    "name": "count_gene_alignments",
                    "version": source["adapter_version"],
                },
                "bytes": source["bytes"],
                "sample_id": source["sample_id"],
                "schema_version": "1.0",
                "sha256": source["sha256"],
            }
            for source in ordered
        ],
        "status": "completed",
    }


def render(report: dict[str, Any]) -> bytes:
    return (json.dumps(
        report,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n").encode("utf-8")


def _unlink_owned(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def write_new(path: Path, payload: bytes, *, root: Path | None = None) -> Path:
    lexical_root = Path.cwd() if root is None else root
    target, directory_fd, target_name = _open_parent(path, lexical_root, "output")
    try:
        try:
            os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(target)

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
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("output write made no progress")
                offset += written
            os.fsync(descriptor)
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
            final_state = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
            if (final_state.st_dev, final_state.st_ino) != identity:
                raise OSError("published output identity differs from staged data")
            if not _unlink_owned(temporary_name, directory_fd, identity):
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
                        if not _unlink_owned(target_name, directory_fd, identity):
                            cleanup_failures.append("published output identity changed")
                    except OSError as cleanup_exc:
                        cleanup_failures.append(
                            f"published output cleanup failed: {cleanup_exc.__class__.__name__}"
                        )
                try:
                    if not _unlink_owned(temporary_name, directory_fd, identity):
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

    def expect(code: str, action: Callable[[], Any]) -> None:
        nonlocal checks
        try:
            action()
        except ContractError as exc:
            if exc.code != code:
                raise RuntimeError(f"expected {code}, got {exc.code}") from exc
        else:
            raise AssertionError(f"{code} case was accepted")
        checks += 1

    contract = {
        "duplicate_primary_records": "duplicate-flag-alone-does-not-exclude; observed-count-reported",
        "feature": "exon",
        "identity": "gene_id",
        "minimum_mapq": 20,
        "missing_nh": "accepted-by-mapq-and-reported",
        "nh_greater_than_one": "unassigned-multimapped",
        "secondary_and_supplementary": "ignored-and-reported",
        "strandedness": "unstranded",
    }

    def fixture(sample_id: str, g_a: Any, g_b: Any) -> dict[str, Any]:
        return {
            "adapter": {"name": "count_gene_alignments", "version": "0.9.0"},
            "analysis_performed": True,
            "assignment_contract": deepcopy(contract),
            "counts": [
                {"contig": "chr2", "count": g_b, "exon_count": 1, "gene_id": "gB", "strand": "-"},
                {"contig": "chr1", "count": g_a, "exon_count": 2, "gene_id": "gA", "strand": "+"},
            ],
            "inputs": {"gtf": {"exon_count": 3, "gene_count": 2, "sha256": "a" * 64}},
            "sample_id": sample_id,
            "schema_version": "1.0",
            "status": "completed",
        }

    def source(report: dict[str, Any]) -> dict[str, Any]:
        payload = render(report)
        return validate_source(payload, report)

    a_report = fixture("sample-a", 2, 1)
    b_report = fixture("sample-b", 0, 3)
    a = source(a_report)
    b = source(b_report)
    report = assemble([b, a])
    matrix = report["matrix"]
    check(matrix["sample_ids"] == ["sample-a", "sample-b"], "sample order differs")
    check([row["gene_id"] for row in matrix["genes"]] == ["gA", "gB"], "gene order differs")
    check(matrix["genes"][0]["counts"] == [2, 0], "gA counts differ")
    check(matrix["genes"][1]["counts"] == [1, 3], "gB counts differ")
    check(matrix["genes"][0]["contig"] == "chr1" and matrix["genes"][1]["strand"] == "-", "gene tuples differ")
    check(report["assignment_contract"] == contract, "assignment contract differs")
    check(report["reference"]["gtf_sha256"] == "a" * 64, "GTF fingerprint differs")
    check([item["sample_id"] for item in report["sources"]] == ["sample-a", "sample-b"], "source order differs")
    check(render(report) == render(assemble([a, b])), "reversed input order changed output")
    check(b"sample-a.json" not in render(report), "output leaked an input path")

    expect("too-few-samples", lambda: assemble([a]))
    expect("duplicate-sample-id", lambda: assemble([a, a]))
    projected_loads = 0

    def oversized_loader(_: Path) -> dict[str, Any]:
        nonlocal projected_loads
        projected_loads += 1
        return {"genes": {f"gene-{index}": {} for index in range(MAX_GENES)}}

    expect(
        "too-many-count-cells",
        lambda: load_sources(
            [Path(f"sample-{index}.json") for index in range(MAX_SAMPLES)],
            oversized_loader,
        ),
    )
    check(projected_loads == 1, "projected cell cap did not stop subsequent source loading")
    mismatch = fixture("sample-b", 0, 3)
    mismatch["inputs"]["gtf"]["sha256"] = "b" * 64
    expect("gtf-fingerprint-mismatch", lambda: assemble([a, source(mismatch)]))
    mismatch = fixture("sample-b", 0, 3)
    mismatch["counts"][0]["exon_count"] = 2
    mismatch["inputs"]["gtf"]["exon_count"] = 4
    expect("gene-tuple-mismatch", lambda: assemble([a, source(mismatch)]))
    mismatch = fixture("sample-b", 0, 3)
    mismatch["counts"].pop()
    mismatch["inputs"]["gtf"] = {"exon_count": 1, "gene_count": 1, "sha256": "a" * 64}
    expect("gene-set-mismatch", lambda: assemble([a, source(mismatch)]))
    mismatch = fixture("sample-b", 0, 3)
    mismatch["assignment_contract"]["minimum_mapq"] = 30
    expect("assignment-contract-mismatch", lambda: assemble([a, source(mismatch)]))

    for bad_count, code in ((True, "invalid-integer"), (-1, "integer-out-of-range"), (1.5, "invalid-integer"), (MAX_SAFE_INTEGER + 1, "integer-out-of-range")):
        bad = fixture("sample-x", bad_count, 0)
        expect(code, lambda bad=bad: source(bad))
    duplicate_gene = fixture("sample-x", 1, 2)
    duplicate_gene["counts"][1]["gene_id"] = "gB"
    expect("duplicate-gene-id", lambda: source(duplicate_gene))
    incomplete = fixture("sample-x", 1, 2)
    incomplete["status"] = "needs-review"
    expect("source-not-completed", lambda: source(incomplete))
    bad_schema = fixture("sample-x", 1, 2)
    bad_schema["schema_version"] = "2.0"
    expect("unsupported-source-schema", lambda: source(bad_schema))
    bad_adapter = fixture("sample-x", 1, 2)
    bad_adapter["adapter"]["name"] = "other"
    expect("unsupported-source-adapter", lambda: source(bad_adapter))
    expect("duplicate-json-key", lambda: parse_json('{"status":"completed","status":"completed"}'))

    with tempfile.TemporaryDirectory(prefix="gene-matrix-selftest-") as temporary_name:
        root = Path(temporary_name)
        a_path = root / "a.json"
        b_path = root / "b.json"
        a_path.write_bytes(render(a_report))
        b_path.write_bytes(render(b_report))
        loaded_a = load_source(a_path, root=root)
        loaded_b = load_source(b_path, root=root)
        check(loaded_a["sample_id"] == "sample-a" and loaded_b["sample_id"] == "sample-b", "source loading differs")
        check(loaded_a["sha256"] == hashlib.sha256(a_path.read_bytes()).hexdigest(), "source hash differs")

        linked = root / "linked.json"
        linked.symlink_to(a_path)
        expect("input-not-regular-file", lambda: load_source(linked, root=root))
        expect("input-parent-traversal", lambda: load_source(Path("..") / "outside.json", root=root))
        real_input_parent = root / "real-input-parent"
        real_input_parent.mkdir()
        (real_input_parent / "source.json").write_bytes(render(a_report))
        linked_input_parent = root / "linked-input-parent"
        linked_input_parent.symlink_to(real_input_parent, target_is_directory=True)
        expect("unsafe-input-parent", lambda: load_source(linked_input_parent / "source.json", root=root))

        output = root / "matrix.json"
        expected = render(assemble([loaded_b, loaded_a]))
        write_new(output, expected, root=root)
        check(output.read_bytes() == expected, "published bytes differ")
        try:
            write_new(output, b"replacement\n", root=root)
        except FileExistsError:
            check(output.read_bytes() == expected, "existing output was replaced")
        else:
            raise AssertionError("existing output was replaced")
        expect("output-parent-traversal", lambda: write_new(Path("..") / "escape.json", expected, root=root))

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        expect("unsafe-output-parent", lambda: write_new(linked_parent / "matrix.json", expected, root=root))
        protected = root / "protected.json"
        protected.write_text("protected\n", encoding="utf-8")
        linked_output = root / "linked-output.json"
        linked_output.symlink_to(protected)
        try:
            write_new(linked_output, expected, root=root)
        except FileExistsError:
            check(protected.read_text(encoding="utf-8") == "protected\n", "output symlink target changed")
        else:
            raise AssertionError("output symlink was accepted")

        rollback_output = root / "rollback.json"
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
                write_new(rollback_output, expected, root=root)
            except OSError:
                check(not rollback_output.exists(), "failed publication left a final output")
                check(not list(root.glob(".rollback.json.tmp-*")), "failed publication left a staged output")
            else:
                raise AssertionError("publication failure was accepted")
        finally:
            os.fsync = original_fsync

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--count-json", nargs="+", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    if arguments.count_json is None or arguments.output is None:
        parser().error("--count-json and --output are required for execution")
    try:
        if not MIN_SAMPLES <= len(arguments.count_json) <= MAX_SAMPLES:
            raise reject("invalid-sample-count", "provide two through 128 source reports")
        sources = load_sources(arguments.count_json)
        report = assemble(sources)
        target = write_new(arguments.output, render(report))
        print(json.dumps({
            "assembly_performed": True,
            "genes": report["matrix"]["gene_count"],
            "output": target.name,
            "samples": report["matrix"]["sample_count"],
            "status": "completed",
        }, sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({
            "assembly_performed": False,
            "code": exc.code,
            "message": exc.message,
            "status": "invalid-input",
        }, sort_keys=True), file=sys.stderr)
        return 2
    except (FileExistsError, FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError) as exc:
        print(json.dumps({
            "assembly_performed": False,
            "error": exc.__class__.__name__,
            "status": "invalid-output",
        }, sort_keys=True), file=sys.stderr)
        return 3
    except OSError as exc:
        print(json.dumps({
            "assembly_performed": False,
            "error": exc.__class__.__name__,
            "status": "io-error",
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
