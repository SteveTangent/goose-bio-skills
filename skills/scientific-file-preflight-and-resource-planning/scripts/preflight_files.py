#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded, read-only preflight report for named local files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "0.6.0"
DEFAULT_PROBE_BYTES = 64 * 1024
MAX_PROBE_BYTES = 1024 * 1024
MIB = 1024 * 1024
GIB = 1024 * MIB
MAX_INPUT_FILES = 256
MAX_TOTAL_PROBE_BYTES = 64 * MIB

RESOURCE_FLOORS = {
    "metadata-only": {
        "scratch_numerator": 0,
        "scratch_denominator": 1,
        "memory_bytes": 16 * MIB,
        "assumption": "bounded metadata/header inspection and one JSON report only",
    },
    "sequential-read": {
        "scratch_numerator": 5,
        "scratch_denominator": 100,
        "memory_bytes": 64 * MIB,
        "assumption": "streaming-style local read; tool output and decompression costs are excluded",
    },
    "indexed-analysis": {
        "scratch_numerator": 5,
        "scratch_denominator": 4,
        "memory_bytes": 512 * MIB,
        "assumption": "index plus working-space triage floor; reference and tool costs are excluded",
    },
    "sort-or-rewrite": {
        "scratch_numerator": 3,
        "scratch_denominator": 1,
        "memory_bytes": GIB,
        "assumption": "rewritten output and temporary-run triage floor; tool behavior may exceed it",
    },
}


class PreflightError(Exception):
    """A declared input or output violates the bounded local contract."""

    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.path is not None:
            result["path"] = self.path
        return result


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def lexical_absolute(raw: str) -> Path:
    if not raw or "\x00" in raw:
        raise PreflightError("invalid-path", "path must be a non-empty string without NUL bytes")
    supplied = Path(raw)
    if ".." in supplied.parts:
        raise PreflightError("parent-traversal", "parent traversal is not allowed", path=raw)
    return Path(os.path.abspath(os.fspath(supplied)))


def lstat_without_leaf_symlink(path: Path) -> os.stat_result:
    if not path.is_absolute():
        raise AssertionError("internal path must be absolute")
    try:
        result = os.lstat(path)
    except FileNotFoundError as exc:
        raise PreflightError("path-not-found", "path does not exist", path=str(path)) from exc
    if stat.S_ISLNK(result.st_mode):
        raise PreflightError("symlink-refused", "a symlink cannot be used as the declared leaf", path=str(path))
    return result


def read_probe(path: Path, probe_bytes: int) -> tuple[os.stat_result, bytes]:
    metadata = lstat_without_leaf_symlink(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise PreflightError("not-regular-file", "input must be a regular file", path=str(path))
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PreflightError("input-open-failed", str(exc), path=str(path)) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise PreflightError("not-regular-file", "opened input is not a regular file", path=str(path))
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise PreflightError("input-changed", "input changed while it was being opened", path=str(path))
        chunks: list[bytes] = []
        remaining = probe_bytes
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        current = os.lstat(path)
        if (
            stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
            or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise PreflightError("input-changed", "input changed during the bounded read", path=str(path))
        return after, b"".join(chunks)
    finally:
        os.close(descriptor)


def suffix_hint(path: Path) -> str | None:
    name = path.name.lower()
    ordered = (
        (".vcf.gz", "gzip-compressed-vcf"),
        (".vcf.bgz", "bgzip-compressed-vcf"),
        (".fastq.gz", "gzip-compressed-fastq"),
        (".fq.gz", "gzip-compressed-fastq"),
        (".fasta.gz", "gzip-compressed-fasta"),
        (".fa.gz", "gzip-compressed-fasta"),
        (".bam", "bam"),
        (".cram", "cram"),
        (".bcf", "bcf"),
        (".vcf", "vcf"),
        (".sam", "sam"),
        (".fastq", "fastq"),
        (".fq", "fastq"),
        (".fasta", "fasta"),
        (".fa", "fasta"),
        (".fna", "fasta"),
        (".bed", "bed-like-text"),
        (".gff", "gff-like-text"),
        (".gff3", "gff-like-text"),
        (".gtf", "gtf-like-text"),
        (".csv", "comma-delimited-text"),
        (".tsv", "tab-delimited-text"),
        (".h5ad", "hdf5"),
        (".h5", "hdf5"),
        (".parquet", "parquet"),
        (".mzml", "mzml-xml"),
    )
    for ending, hint in ordered:
        if name.endswith(ending):
            return hint
    return None


def detect_probe(data: bytes) -> tuple[str, str]:
    signatures = (
        (b"\x1f\x8b", "gzip-stream", "high"),
        (b"BZh", "bzip2-stream", "high"),
        (b"\xfd7zXZ\x00", "xz-stream", "high"),
        (b"PK\x03\x04", "zip-container", "high"),
        (b"BAM\x01", "bam", "high"),
        (b"CRAM", "cram", "high"),
        (b"BCF\x02", "bcf", "high"),
        (b"\x89HDF\r\n\x1a\n", "hdf5", "high"),
        (b"PAR1", "parquet", "high"),
        (b"SQLite format 3\x00", "sqlite", "high"),
    )
    for signature, detected, confidence in signatures:
        if data.startswith(signature):
            return detected, confidence
    if not data:
        return "empty", "high"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "unrecognized-binary", "low"
    stripped = text.lstrip()
    lines = stripped.splitlines()
    first = lines[0] if lines else ""
    if first.startswith("##fileformat=VCF"):
        return "vcf-text", "high"
    if first.startswith(("@HD\t", "@SQ\t", "@RG\t", "@PG\t")):
        return "sam-text", "medium"
    if first.startswith(">"):
        return "fasta-text", "medium"
    if len(lines) >= 3 and first.startswith("@") and lines[2].startswith("+"):
        return "fastq-text", "medium"
    lowered = stripped[:512].lower()
    if lowered.startswith("<?xml") or lowered.startswith("<mzml"):
        return "xml-text", "medium"
    if first.startswith(("{", "[")):
        return "json-like-text", "low"
    return "text", "low"


def expected_magic_warning(hint: str | None, detected: str) -> list[str]:
    if hint is None:
        return []
    expected: dict[str, set[str]] = {
        "bam": {"bam", "gzip-stream"},
        "cram": {"cram"},
        "bcf": {"bcf", "gzip-stream"},
        "hdf5": {"hdf5"},
        "parquet": {"parquet"},
        "gzip-compressed-vcf": {"gzip-stream"},
        "bgzip-compressed-vcf": {"gzip-stream"},
        "gzip-compressed-fastq": {"gzip-stream"},
        "gzip-compressed-fasta": {"gzip-stream"},
    }
    if hint in expected and detected not in expected[hint]:
        return ["suffix-magic-not-confirmed"]
    return []


def companion_candidates(path: Path, hint: str | None) -> list[Path]:
    candidates: list[Path] = []
    if hint == "bam":
        candidates.extend((Path(f"{path}.bai"), path.with_suffix(".bai")))
    elif hint == "cram":
        candidates.extend((Path(f"{path}.crai"), path.with_suffix(".crai")))
    elif hint in {"gzip-compressed-vcf", "bgzip-compressed-vcf"}:
        candidates.extend((Path(f"{path}.tbi"), Path(f"{path}.csi")))
    elif hint == "bcf":
        candidates.append(Path(f"{path}.csi"))
    elif hint == "fasta":
        candidates.append(Path(f"{path}.fai"))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def companion_state(path: Path) -> dict[str, str]:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return {"path": str(path), "state": "missing"}
    if stat.S_ISLNK(metadata.st_mode):
        state = "unsafe-symlink"
    elif stat.S_ISREG(metadata.st_mode):
        state = "present-unvalidated"
    else:
        state = "present-nonregular"
    return {"path": str(path), "state": state}


def inspect_file(raw_path: str, probe_bytes: int) -> dict[str, Any]:
    path = lexical_absolute(raw_path)
    metadata, probe = read_probe(path, probe_bytes)
    hint = suffix_hint(path)
    detected, confidence = detect_probe(probe)
    warnings = expected_magic_warning(hint, detected)
    if metadata.st_size == 0:
        warnings.append("empty-file")
    return {
        "path": str(path),
        "size_bytes": metadata.st_size,
        "mode": oct(stat.S_IMODE(metadata.st_mode)),
        "modified_at": datetime.fromtimestamp(metadata.st_mtime, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "bytes_inspected": len(probe),
        "probe_sha256": hashlib.sha256(probe).hexdigest(),
        "probe_covers_whole_file": len(probe) == metadata.st_size,
        "whole_file_hash": None,
        "suffix_hint": hint,
        "detected_container": detected,
        "detection_confidence": confidence,
        "companion_candidates": [
            companion_state(candidate) for candidate in companion_candidates(path, hint)
        ],
        "warnings": warnings,
    }


def budget_state(budget: int | None, floor: int) -> str:
    if budget is None:
        return "not-supplied"
    return "at-or-above-planning-floor" if budget >= floor else "below-planning-floor"


def resource_plan(
    total_input_bytes: int,
    operation: str,
    disk_budget_bytes: int | None,
    memory_budget_bytes: int | None,
) -> dict[str, Any]:
    policy = RESOURCE_FLOORS[operation]
    numerator = int(policy["scratch_numerator"])
    denominator = int(policy["scratch_denominator"])
    scratch = (total_input_bytes * numerator + denominator - 1) // denominator + MIB
    memory = int(policy["memory_bytes"])
    return {
        "operation_class": operation,
        "scratch_space_planning_floor_bytes": scratch,
        "memory_planning_floor_bytes": memory,
        "disk_budget_bytes": disk_budget_bytes,
        "disk_budget_assessment": budget_state(disk_budget_bytes, scratch),
        "memory_budget_bytes": memory_budget_bytes,
        "memory_budget_assessment": budget_state(memory_budget_bytes, memory),
        "assumption": policy["assumption"],
        "not_included": [
            "reference-data storage",
            "tool-specific indexes and caches",
            "decompressed-size expansion",
            "scheduler or concurrency overhead",
            "tool-specific output size",
        ],
    }


def build_report(
    raw_paths: list[str],
    *,
    operation: str,
    probe_bytes: int,
    disk_budget_bytes: int | None,
    memory_budget_bytes: int | None,
) -> dict[str, Any]:
    if not raw_paths:
        raise PreflightError("missing-input", "at least one --input is required")
    if len(raw_paths) > MAX_INPUT_FILES:
        raise PreflightError(
            "too-many-inputs",
            f"at most {MAX_INPUT_FILES} explicitly named inputs are allowed",
        )
    if not 1 <= probe_bytes <= MAX_PROBE_BYTES:
        raise PreflightError("invalid-probe-cap", f"probe cap must be between 1 and {MAX_PROBE_BYTES}")
    planned_probe_ceiling = len(raw_paths) * probe_bytes
    if planned_probe_ceiling > MAX_TOTAL_PROBE_BYTES:
        raise PreflightError(
            "total-probe-cap-exceeded",
            f"declared inputs and per-file cap may inspect at most {MAX_TOTAL_PROBE_BYTES} bytes total",
        )
    if operation not in RESOURCE_FLOORS:
        raise PreflightError("invalid-operation", "unsupported operation class")
    for label, value in (("disk", disk_budget_bytes), ("memory", memory_budget_bytes)):
        if value is not None and value < 0:
            raise PreflightError("invalid-budget", f"{label} budget must be non-negative")
    normalized = [lexical_absolute(path) for path in raw_paths]
    keys = [os.path.normcase(str(path)) for path in normalized]
    if len(keys) != len(set(keys)):
        raise PreflightError("duplicate-input", "the same lexical input path was supplied more than once")
    files = [inspect_file(str(path), probe_bytes) for path in normalized]
    total_input = sum(int(item["size_bytes"]) for item in files)
    total_inspected = sum(int(item["bytes_inspected"]) for item in files)
    warnings = sorted({warning for item in files for warning in item["warnings"]})
    return {
        "schema_version": "0.1.0",
        "tool": "preflight_files.py",
        "tool_version": VERSION,
        "python_version": platform.python_version(),
        "status": "completed",
        "preflight_performed": True,
        "scientific_validation_performed": False,
        "created_at": now_utc(),
        "limits": {
            "probe_bytes_per_file": probe_bytes,
            "max_input_files": MAX_INPUT_FILES,
            "max_total_probe_bytes": MAX_TOTAL_PROBE_BYTES,
            "planned_probe_ceiling_bytes": planned_probe_ceiling,
            "recursive_traversal": False,
            "decompression": False,
            "whole_file_hashing": False,
            "network": False,
            "subprocess": False,
        },
        "summary": {
            "file_count": len(files),
            "total_input_bytes": total_input,
            "total_bytes_inspected": total_inspected,
        },
        "files": files,
        "resource_plan": resource_plan(
            total_input,
            operation,
            disk_budget_bytes,
            memory_budget_bytes,
        ),
        "warnings": warnings,
        "limitations": [
            "Container clues do not establish syntax, semantic, or scientific validity.",
            "Companion files are presence-checked only and are not parsed.",
            "Resource values are planning floors, not measured runtime predictions.",
        ],
    }


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def unlink_if_owned(target: Path, temporary: Path) -> None:
    try:
        target_state = os.lstat(target)
        temporary_state = os.lstat(temporary)
        if (
            stat.S_ISREG(target_state.st_mode)
            and (target_state.st_dev, target_state.st_ino)
            == (temporary_state.st_dev, temporary_state.st_ino)
        ):
            target.unlink()
    except FileNotFoundError:
        pass


def write_new_json(raw_path: str, report: dict[str, Any]) -> Path:
    supplied = Path(raw_path)
    if ".." in supplied.parts:
        raise PreflightError("parent-traversal", "output parent traversal is not allowed", path=raw_path)
    target = lexical_absolute(raw_path)
    parent = target.parent
    parent_metadata = lstat_without_leaf_symlink(parent)
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise PreflightError("output-parent-not-directory", "output parent must be an existing directory", path=str(parent))
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    else:
        raise PreflightError("output-exists", "output already exists; overwrite is forbidden", path=str(target))

    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=parent)
    temporary = Path(temporary_name)
    published = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise PreflightError("output-exists", "output already exists; overwrite is forbidden", path=str(target)) from exc
        published = True
        fsync_directory(parent)
    except BaseException:
        if published:
            unlink_if_owned(target, temporary)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return target


def expect_error(code: str, action: Any) -> None:
    try:
        action()
    except PreflightError as exc:
        if exc.code != code:
            raise AssertionError(f"expected {code}, got {exc.code}") from exc
    else:
        raise AssertionError(f"expected {code}")


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="bio02-preflight-test-") as temporary:
        root = Path(temporary)
        fasta = root / "sample.fa"
        fasta.write_bytes(b">seq1\n" + b"ACGT" * 80 + b"\n")
        bam = root / "reads.bam"
        bam.write_bytes(b"\x1f\x8b" + b"x" * 100)
        Path(f"{bam}.bai").write_bytes(b"index")

        report = build_report(
            [str(fasta), str(bam)],
            operation="indexed-analysis",
            probe_bytes=32,
            disk_budget_bytes=10 * MIB,
            memory_budget_bytes=GIB,
        )
        if report["summary"]["file_count"] != 2:
            raise AssertionError("file count differs")
        if report["summary"]["total_bytes_inspected"] != 64:
            raise AssertionError("bounded probe count differs")
        if report["files"][0]["detected_container"] != "fasta-text":
            raise AssertionError("FASTA clue differs")
        companions = report["files"][1]["companion_candidates"]
        if not any(item["state"] == "present-unvalidated" for item in companions):
            raise AssertionError("BAM companion was not detected")

        tiny = root / "tiny.tsv"
        tiny.write_bytes(b"a\tb\n")
        tiny_report = inspect_file(str(tiny), 16)
        if tiny_report["probe_covers_whole_file"] is not True or tiny_report["whole_file_hash"] is not None:
            raise AssertionError("small-file probe disclosure differs")

        compressed_bcf = root / "calls.bcf"
        compressed_bcf.write_bytes(b"\x1f\x8b" + b"compressed-bcf-probe")
        bcf_report = inspect_file(str(compressed_bcf), 16)
        if "suffix-magic-not-confirmed" in bcf_report["warnings"]:
            raise AssertionError("compressed BCF was incorrectly rejected")

        symlink = root / "linked.fa"
        os.symlink(fasta, symlink)
        expect_error(
            "symlink-refused",
            lambda: build_report(
                [str(symlink)],
                operation="metadata-only",
                probe_bytes=16,
                disk_budget_bytes=None,
                memory_budget_bytes=None,
            ),
        )

        expect_error(
            "too-many-inputs",
            lambda: build_report(
                [str(fasta)] * (MAX_INPUT_FILES + 1),
                operation="metadata-only",
                probe_bytes=1,
                disk_budget_bytes=None,
                memory_budget_bytes=None,
            ),
        )
        expect_error(
            "total-probe-cap-exceeded",
            lambda: build_report(
                [str(fasta)] * 65,
                operation="metadata-only",
                probe_bytes=MAX_PROBE_BYTES,
                disk_budget_bytes=None,
                memory_budget_bytes=None,
            ),
        )

        fifo = root / "named-pipe"
        if hasattr(os, "mkfifo"):
            os.mkfifo(fifo)
            expect_error(
                "not-regular-file",
                lambda: build_report(
                    [str(fifo)],
                    operation="metadata-only",
                    probe_bytes=16,
                    disk_budget_bytes=None,
                    memory_budget_bytes=None,
                ),
            )

        output = root / "report.json"
        write_new_json(str(output), report)
        original = output.read_bytes()
        expect_error("output-exists", lambda: write_new_json(str(output), report))
        if output.read_bytes() != original:
            raise AssertionError("existing output changed")

        owned_temp = root / "owned.tmp"
        owned_target = root / "owned.json"
        replacement = root / "replacement.json"
        owned_temp.write_bytes(b"owned")
        os.link(owned_temp, owned_target)
        replacement.write_bytes(b"concurrent-replacement")
        os.replace(replacement, owned_target)
        unlink_if_owned(owned_target, owned_temp)
        if owned_target.read_bytes() != b"concurrent-replacement":
            raise AssertionError("cleanup removed a replacement it did not own")

    print(json.dumps({"checks": 11, "status": "pass", "version": VERSION}, sort_keys=True))


def nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def probe_int(value: str) -> int:
    parsed = nonnegative_int(value)
    if not 1 <= parsed <= MAX_PROBE_BYTES:
        raise argparse.ArgumentTypeError(f"probe bytes must be between 1 and {MAX_PROBE_BYTES}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--operation", choices=tuple(RESOURCE_FLOORS))
    parser.add_argument("--output")
    parser.add_argument("--probe-bytes", type=probe_int, default=DEFAULT_PROBE_BYTES)
    parser.add_argument("--disk-budget-bytes", type=nonnegative_int)
    parser.add_argument("--memory-budget-bytes", type=nonnegative_int)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        if args.input or args.operation or args.output:
            print(json.dumps({"status": "invalid-input", "error": {"code": "self-test-argument-conflict"}}), file=sys.stderr)
            return 2
        self_test()
        return 0
    if not args.input or args.operation is None or args.output is None:
        print(
            json.dumps(
                {
                    "status": "invalid-input",
                    "error": {
                        "code": "missing-required-argument",
                        "message": "--input, --operation, and --output are required",
                    },
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        report = build_report(
            args.input,
            operation=args.operation,
            probe_bytes=args.probe_bytes,
            disk_budget_bytes=args.disk_budget_bytes,
            memory_budget_bytes=args.memory_budget_bytes,
        )
        output = write_new_json(args.output, report)
    except (PreflightError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, PreflightError) else {
            "code": "filesystem-error",
            "message": str(exc),
        }
        print(json.dumps({"status": "invalid-input", "error": error}, sort_keys=True), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "files": report["summary"]["file_count"],
                "bytes_inspected": report["summary"]["total_bytes_inspected"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
