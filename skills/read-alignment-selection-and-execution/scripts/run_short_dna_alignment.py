#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one bounded short genomic DNA alignment with pinned minimap2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator


VERSION = "0.7.0"
EXPECTED_MINIMAP2_VERSION = "2.31-r1302"
MAX_REFERENCE_BYTES = 16 * 1024 * 1024
MAX_READS_BYTES = 16 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_SAM_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_LINE_BYTES = 1024 * 1024
MAX_SEQUENCE_BASES = 5_000_000
MIN_READ_BASES = 20
MAX_READ_BASES = 1_000
TIMEOUT_SECONDS = 120
SAFE_NAME = re.compile(r"[^\x00-\x20\x7f]+\Z")
HEX_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MINIMAP2_VERSION = re.compile(r"2\.31-r1302\Z")
DNA = frozenset(b"ACGTNacgtn")
CIGAR = re.compile(rb"(?:[1-9][0-9]*[MIDNSHP=X])+\Z")
FIXED_OPTIONS = ("-a", "-x", "sr", "-t", "1", "--seed", "11", "--secondary=no")


class ContractError(Exception):
    """A structured fail-closed result safe to expose."""

    def __init__(self, status: str, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def fail(status: str, code: str, message: str) -> ContractError:
    return ContractError(status, code, message)


def _validate_lexical_path(path: Path, role: str) -> None:
    raw = os.fspath(path)
    if not raw or "\x00" in raw or ".." in path.parts:
        raise fail("invalid-input", f"invalid-{role}-path", f"{role} path is invalid")


@contextmanager
def _pinned_regular(
    path: Path,
    role: str,
    *,
    failure_status: str,
    unavailable_code: str,
    require_executable: bool = False,
) -> Iterator[tuple[Path, int, os.stat_result]]:
    """Resolve ordinary symlinks, then pin and verify the final regular file."""
    raw = os.fspath(path)
    if not raw or "\x00" in raw:
        raise fail("invalid-input", f"invalid-{role}-path", f"{role} path is invalid")
    descriptor = -1
    try:
        canonical = Path(os.path.abspath(path)).resolve(strict=True)
        identified = canonical.stat(follow_symlinks=False)
        if not stat.S_ISREG(identified.st_mode):
            raise OSError("not regular")
        if require_executable and not os.access(canonical, os.X_OK):
            raise OSError("not executable")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(canonical, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (identified.st_dev, identified.st_ino):
            raise OSError("target changed")
        if require_executable and not opened.st_mode & 0o111:
            raise OSError("not executable")
        yield canonical, descriptor, opened
    except ContractError:
        raise
    except (OSError, RuntimeError) as exc:
        raise fail(failure_status, unavailable_code, f"{role} is unavailable or unsafe") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _relative_inside_root(path: Path, root: Path, role: str) -> Path:
    _validate_lexical_path(path, role)
    supplied = Path(os.path.abspath(path))
    lexical_cwd = Path(os.getcwd())
    candidates = [lexical_cwd, root]
    if os.fspath(lexical_cwd).startswith("/private/"):
        candidates.append(Path(os.fspath(lexical_cwd)[8:]))
    if os.fspath(root).startswith("/private/"):
        candidates.append(Path(os.fspath(root)[8:]))
    relative_to_cwd: Path | None = None
    for candidate in candidates:
        try:
            relative_to_cwd = supplied.relative_to(candidate)
            break
        except ValueError:
            continue
    if relative_to_cwd is None:
        raise fail("invalid-input", f"{role}-outside-cwd", f"{role} must remain inside cwd")
    lexical = root / relative_to_cwd
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise fail("invalid-input", f"{role}-outside-cwd", f"{role} must remain inside cwd") from exc
    if not relative.parts:
        raise fail("invalid-input", f"invalid-{role}-path", f"{role} must be a leaf path")
    return relative


def _open_directory_chain(root: Path, parts: tuple[str, ...], role: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
        try:
            for part in parts:
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise
    except ContractError:
        raise
    except OSError as exc:
        raise fail("invalid-input", f"unsafe-{role}-parent", f"{role} parent is unsafe") from exc


@contextmanager
def _bounded_input(path: Path, role: str, limit: int) -> Iterator[tuple[Path, bytes]]:
    with _pinned_regular(
        path,
        role,
        failure_status="invalid-input",
        unavailable_code=f"unreadable-{role}",
    ) as (canonical, descriptor, opened):
        if opened.st_size > limit:
            raise fail("needs-tool", f"{role}-too-large", f"{role} exceeds the preview byte limit")
        payload = bytearray()
        while len(payload) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > limit:
            raise fail("needs-tool", f"{role}-too-large", f"{role} exceeds the preview byte limit")
        if any(getattr(opened, field) != getattr(after, field) for field in stable):
            raise fail("invalid-input", f"{role}-changed", f"{role} changed while reading")
        yield canonical, bytes(payload)


def _ascii_lines(payload: bytes, role: str) -> list[bytes]:
    if b"\x00" in payload:
        raise fail("invalid-input", f"invalid-{role}", f"{role} contains a NUL byte")
    try:
        payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise fail("invalid-input", f"non-ascii-{role}", f"{role} must be plain ASCII") from exc
    lines = payload.splitlines()
    if not lines or any(len(line) > MAX_LINE_BYTES for line in lines):
        raise fail("invalid-input", f"invalid-{role}", f"{role} is empty or has an oversized line")
    return lines


def _valid_name(raw: bytes, role: str) -> str:
    try:
        name = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise fail("invalid-input", f"invalid-{role}-name", f"{role} name must be ASCII") from exc
    if not name or not SAFE_NAME.fullmatch(name) or name[0] in {"@", ">"}:
        raise fail("invalid-input", f"invalid-{role}-name", f"{role} name is unsafe")
    return name


def parse_fasta(payload: bytes) -> dict[str, Any]:
    lines = _ascii_lines(payload, "reference")
    names: list[str] = []
    lengths: list[int] = []
    seen: set[str] = set()
    current = -1
    total_bases = 0
    for line in lines:
        if line.startswith(b">"):
            name_token = line[1:].split(None, 1)[0]
            name = _valid_name(name_token, "reference")
            if name in seen:
                raise fail("invalid-input", "duplicate-reference-name", "reference names must be unique")
            seen.add(name)
            names.append(name)
            lengths.append(0)
            current += 1
            continue
        if current < 0 or not line or any(base not in DNA for base in line):
            raise fail("invalid-input", "invalid-reference-fasta", "reference must be strict DNA FASTA")
        lengths[current] += len(line)
        total_bases += len(line)
        if total_bases > MAX_SEQUENCE_BASES:
            raise fail("needs-tool", "reference-too-many-bases", "reference exceeds the preview base limit")
    if not names or any(length == 0 for length in lengths):
        raise fail("invalid-input", "empty-reference-sequence", "every reference record needs sequence")
    return {
        "records": len(names),
        "bases": total_bases,
        "sequences": [{"name": name, "length": length} for name, length in zip(names, lengths, strict=True)],
    }


def parse_fastq(payload: bytes) -> dict[str, Any]:
    lines = _ascii_lines(payload, "reads")
    if len(lines) % 4 != 0:
        raise fail("invalid-input", "invalid-fastq-record-shape", "FASTQ must contain four-line records")
    names: list[str] = []
    seen: set[str] = set()
    total_bases = 0
    minimum: int | None = None
    maximum = 0
    records_by_name: dict[str, dict[str, str]] = {}
    for offset in range(0, len(lines), 4):
        header, sequence, plus, quality = lines[offset:offset + 4]
        if not header.startswith(b"@") or not plus.startswith(b"+"):
            raise fail("invalid-input", "invalid-fastq-markers", "FASTQ record markers are invalid")
        if plus != b"+" and plus[1:] != header[1:]:
            raise fail(
                "invalid-input",
                "fastq-plus-identifier-mismatch",
                "FASTQ plus-line identifier must be empty or exactly repeat the header",
            )
        name = _valid_name(header[1:].split(None, 1)[0], "read")
        if name.endswith("/1") or name.endswith("/2"):
            raise fail("invalid-input", "paired-read-name-refused", "paired-end-style read names are excluded")
        if name in seen:
            raise fail("invalid-input", "duplicate-read-name", "read names must be unique")
        seen.add(name)
        if not sequence or any(base not in DNA for base in sequence):
            raise fail("invalid-input", "invalid-read-sequence", "reads must contain only A/C/G/T/N")
        if len(sequence) != len(quality) or any(score < 33 or score > 126 for score in quality):
            raise fail("invalid-input", "invalid-read-quality", "FASTQ quality must be printable Phred+33 length-matched text")
        if not MIN_READ_BASES <= len(sequence) <= MAX_READ_BASES:
            raise fail("needs-tool", "read-length-out-of-scope", "read length is outside the short-read preview range")
        names.append(name)
        records_by_name[name] = {
            "sequence": sequence.decode("ascii").upper(),
            "quality": quality.decode("ascii"),
        }
        total_bases += len(sequence)
        minimum = len(sequence) if minimum is None else min(minimum, len(sequence))
        maximum = max(maximum, len(sequence))
        if len(names) > MAX_RECORDS:
            raise fail("needs-tool", "too-many-reads", "read count exceeds the preview limit")
    if not names:
        raise fail("invalid-input", "empty-fastq", "FASTQ must contain at least one read")
    return {
        "records": len(names),
        "bases": total_bases,
        "minimum_length": minimum,
        "maximum_length": maximum,
        "names": names,
        "records_by_name": records_by_name,
    }


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_executable(path: Path, expected_digest: str | None) -> tuple[bytes, str]:
    if expected_digest is not None and not HEX_DIGEST.fullmatch(expected_digest):
        raise fail("invalid-input", "invalid-minimap2-digest", "minimap2 SHA-256 must be lowercase 64-hex")
    with _pinned_regular(
        path,
        "minimap2",
        failure_status="needs-tool",
        unavailable_code="minimap2-unavailable",
        require_executable=True,
    ) as (_, descriptor, opened):
        if opened.st_size > MAX_EXECUTABLE_BYTES:
            raise fail("needs-tool", "minimap2-too-large", "minimap2 exceeds the preview byte limit")
        payload = bytearray()
        while len(payload) <= MAX_EXECUTABLE_BYTES:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_EXECUTABLE_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > MAX_EXECUTABLE_BYTES:
            raise fail("needs-tool", "minimap2-too-large", "minimap2 exceeds the preview byte limit")
        if any(getattr(opened, field) != getattr(after, field) for field in stable):
            raise fail("needs-tool", "minimap2-changed", "minimap2 changed while fingerprinting")
        payload = bytes(payload)
    actual = sha256(payload)
    if expected_digest is not None and actual != expected_digest:
        raise fail("needs-tool", "minimap2-digest-mismatch", "minimap2 SHA-256 differs from the approved executable")
    return payload, actual


def clean_environment(directory: Path) -> dict[str, str]:
    return {
        "HOME": str(directory),
        "LANG": "C",
        "LC_ALL": "C",
        "MM2_NO_KALLOC": "1",
        "PATH": os.defpath,
        "TMPDIR": str(directory),
        "TZ": "UTC",
    }


def run_process(command: list[str], directory: Path, stdout: BinaryIO | int) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            command,
            cwd=directory,
            env=clean_environment(directory),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise fail("needs-tool", "minimap2-execution-failed", "minimap2 could not complete") from exc


def check_version(executable: str, directory: Path) -> str:
    completed = run_process([executable, "--version"], directory, subprocess.PIPE)
    if completed.returncode != 0 or completed.stderr or len(completed.stdout) > 128:
        raise fail("needs-tool", "minimap2-version-check-failed", "minimap2 version check failed closed")
    try:
        version = completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise fail("needs-tool", "invalid-minimap2-version", "minimap2 version output is invalid") from exc
    if not MINIMAP2_VERSION.fullmatch(version):
        raise fail("needs-tool", "unsupported-minimap2-version", "exact minimap2 2.31-r1302 is required")
    return version


def copy_private(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def _sam_decimal(raw: bytes, role: str, maximum: int) -> int:
    if not raw or not raw.isdigit() or len(raw) > len(str(maximum)):
        raise fail("needs-tool", "invalid-sam-record", f"minimap2 returned an invalid SAM {role}")
    value = int(raw)
    if value > maximum:
        raise fail("needs-tool", "invalid-sam-record", f"minimap2 returned an invalid SAM {role}")
    return value


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]


def parse_sam(payload: bytes, reads: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    if len(payload) > MAX_SAM_BYTES:
        raise fail("needs-tool", "sam-too-large", "SAM exceeds the preview byte limit")
    lines = _ascii_lines(payload, "sam")
    header_count = 0
    records = 0
    primary_by_name: dict[str, int] = {}
    expected_reads: dict[str, dict[str, str]] = reads["records_by_name"]
    expected_references = {entry["name"]: entry["length"] for entry in reference["sequences"]}
    observed_references: dict[str, int] = {}
    mapped = 0
    unmapped = 0
    for line in lines:
        if line.startswith(b"@"):
            if records:
                raise fail("needs-tool", "invalid-sam-header-order", "minimap2 returned an invalid SAM header order")
            header_count += 1
            fields = line.split(b"\t")
            if fields[0] not in {b"@HD", b"@SQ", b"@RG", b"@PG", b"@CO"}:
                raise fail("needs-tool", "invalid-sam-header", "minimap2 returned an unsupported SAM header")
            if fields[0] == b"@SQ":
                tags: dict[bytes, bytes] = {}
                for field in fields[1:]:
                    if b":" not in field:
                        raise fail("needs-tool", "invalid-sam-header", "minimap2 returned a malformed @SQ header")
                    tag, value = field.split(b":", 1)
                    if len(tag) != 2 or tag in tags:
                        raise fail("needs-tool", "invalid-sam-header", "minimap2 returned a malformed @SQ header")
                    tags[tag] = value
                if b"SN" not in tags or b"LN" not in tags:
                    raise fail("needs-tool", "invalid-sam-header", "minimap2 returned an incomplete @SQ header")
                try:
                    sequence_name = tags[b"SN"].decode("ascii")
                except UnicodeDecodeError as exc:
                    raise fail("needs-tool", "invalid-sam-header", "minimap2 returned a malformed @SQ name") from exc
                sequence_length = _sam_decimal(tags[b"LN"], "@SQ length", MAX_SEQUENCE_BASES)
                if sequence_length == 0 or sequence_name in observed_references:
                    raise fail("needs-tool", "invalid-sam-header", "minimap2 returned a duplicate or empty @SQ header")
                observed_references[sequence_name] = sequence_length
            continue
        records += 1
        fields = line.split(b"\t")
        if len(fields) < 11:
            raise fail("needs-tool", "invalid-sam-record", "minimap2 returned a malformed SAM record")
        try:
            name = fields[0].decode("ascii")
            reference_name = fields[2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise fail("needs-tool", "invalid-sam-record", "minimap2 returned a malformed SAM record") from exc
        flag = _sam_decimal(fields[1], "FLAG", 65535)
        position = _sam_decimal(fields[3], "POS", MAX_SEQUENCE_BASES)
        mapping_quality = _sam_decimal(fields[4], "MAPQ", 255)
        if name not in expected_reads:
            raise fail("needs-tool", "unexpected-sam-record", "minimap2 returned an unexpected SAM record")
        if flag & 0x100 or flag & 0x800:
            raise fail("needs-tool", "secondary-sam-record-refused", "minimap2 returned a secondary or supplementary SAM record")
        if flag not in {0, 4, 16}:
            raise fail("needs-tool", "unexpected-sam-flags", "minimap2 returned flags outside the fixed single-end contract")
        if fields[6] != b"*" or fields[7] != b"0" or fields[8] != b"0":
            raise fail("needs-tool", "invalid-sam-mate-fields", "minimap2 returned mate fields for single-end reads")
        expected = expected_reads[name]
        try:
            sequence = fields[9].decode("ascii").upper()
            quality = fields[10].decode("ascii")
        except UnicodeDecodeError as exc:
            raise fail("needs-tool", "invalid-sam-sequence", "minimap2 returned non-ASCII sequence evidence") from exc
        expected_sequence = expected["sequence"] if flag != 16 else _reverse_complement(expected["sequence"])
        expected_quality = expected["quality"] if flag != 16 else expected["quality"][::-1]
        if sequence != expected_sequence or quality != expected_quality:
            raise fail("needs-tool", "sam-read-evidence-mismatch", "SAM sequence or quality differs from the FASTQ read")
        primary_by_name[name] = primary_by_name.get(name, 0) + 1
        if flag & 0x4:
            if flag != 4 or reference_name != "*" or position != 0 or mapping_quality != 0 or fields[5] != b"*":
                raise fail("needs-tool", "invalid-unmapped-sam-record", "minimap2 returned incoherent unmapped fields")
            unmapped += 1
        else:
            if reference_name not in expected_references:
                raise fail("needs-tool", "unknown-sam-reference", "SAM alignment names an unknown reference")
            if position == 0 or not CIGAR.fullmatch(fields[5]):
                raise fail("needs-tool", "invalid-sam-cigar", "minimap2 returned an invalid mapped CIGAR")
            operations = [(int(length), operator) for length, operator in re.findall(rb"([1-9][0-9]*)([MIDNSHP=X])", fields[5])]
            operators = [operator for _, operator in operations]
            if any(operator in {b"H", b"P", b"N"} for operator in operators):
                raise fail("needs-tool", "unsupported-sam-cigar-operation", "SAM CIGAR uses an operation outside the fixed DNA branch")
            if any(operator == b"S" and index not in {0, len(operators) - 1} for index, operator in enumerate(operators)):
                raise fail("needs-tool", "invalid-sam-cigar-clipping", "SAM soft clipping must be terminal")
            if not any(operator in {b"M", b"=", b"X"} for operator in operators):
                raise fail("needs-tool", "sam-cigar-without-alignment", "SAM CIGAR has no aligned query bases")
            query_bases = sum(length for length, operator in operations if operator in {b"M", b"I", b"S", b"=", b"X"})
            reference_bases = sum(length for length, operator in operations if operator in {b"M", b"D", b"N", b"=", b"X"})
            if query_bases != len(expected_sequence) or reference_bases == 0:
                raise fail("needs-tool", "sam-cigar-length-mismatch", "SAM CIGAR does not reconcile with the FASTQ read")
            if position + reference_bases - 1 > expected_references[reference_name]:
                raise fail("needs-tool", "sam-reference-span-invalid", "SAM alignment extends beyond the reference")
            mapped += 1
    if observed_references != expected_references:
        raise fail("needs-tool", "sam-reference-dictionary-mismatch", "SAM @SQ headers do not match the FASTA reference")
    if header_count == 0 or set(primary_by_name) != set(expected_reads) or any(count != 1 for count in primary_by_name.values()):
        raise fail("needs-tool", "primary-record-reconciliation-failed", "primary SAM records do not match FASTQ reads")
    return {
        "header_lines": header_count,
        "alignment_records": records,
        "primary_records": mapped + unmapped,
        "mapped_primary_reads": mapped,
        "unmapped_primary_reads": unmapped,
    }


def analyze(
    *,
    reference_path: Path,
    reads_path: Path,
    executable_path: Path,
    expected_executable_digest: str | None,
    declared_single_end_short_genomic_dna: bool,
) -> tuple[bytes, dict[str, Any]]:
    if not declared_single_end_short_genomic_dna:
        raise fail("needs-decision", "missing-assay-declaration", "single-end short genomic DNA must be declared")
    executable_payload, executable_digest = resolve_executable(executable_path, expected_executable_digest)
    with _bounded_input(reference_path, "reference", MAX_REFERENCE_BYTES) as (_, reference_payload), \
            _bounded_input(reads_path, "reads", MAX_READS_BYTES) as (_, reads_payload):
        reference = parse_fasta(reference_payload)
        reads = parse_fastq(reads_payload)
        with tempfile.TemporaryDirectory(prefix="bio02-short-dna-align-") as temporary:
            directory = Path(temporary)
            os.chmod(directory, 0o700)
            private_reference = directory / "reference.fa"
            private_reads = directory / "reads.fastq"
            private_sam = directory / "alignment.sam"
            private_executable = directory / "minimap2"
            copy_private(private_reference, reference_payload)
            copy_private(private_reads, reads_payload)
            copy_private(private_executable, executable_payload)
            private_executable.chmod(0o700)
            version = check_version("./minimap2", directory)
            command = ["./minimap2", *FIXED_OPTIONS, private_reference.name, private_reads.name]
            with private_sam.open("xb") as stdout:
                completed = run_process(command, directory, stdout)
                stdout.flush()
                os.fsync(stdout.fileno())
            if completed.returncode != 0:
                raise fail("needs-tool", "minimap2-failed", "minimap2 failed closed")
            if len(completed.stderr) > 64 * 1024:
                raise fail("needs-tool", "minimap2-stderr-too-large", "minimap2 diagnostics exceeded the limit")
            sam_payload = private_sam.read_bytes()
            sam = parse_sam(sam_payload, reads, reference)
    command_template = ["minimap2", *FIXED_OPTIONS, "reference.fa", "reads.fastq"]
    report = {
        "schema_version": "1.0",
        "status": "completed",
        "analysis_performed": True,
        "tool": {
            "name": "minimap2",
            "version": version,
            "executable_sha256": executable_digest,
            "adapter": "run_short_dna_alignment",
            "adapter_version": VERSION,
        },
        "command_contract": {
            "argv_template": command_template,
            "preset": "sr",
            "threads": 1,
            "seed": 11,
            "secondary_alignments": "disabled",
            "shell": False,
            "network": False,
        },
        "inputs": {
            "reference": {
                "sha256": sha256(reference_payload),
                "bytes": len(reference_payload),
                **reference,
            },
            "reads": {
                "sha256": sha256(reads_payload),
                "bytes": len(reads_payload),
                **{key: value for key, value in reads.items() if key not in {"names", "records_by_name"}},
                "layout": "single-end",
                "assay": "short-genomic-dna",
            },
        },
        "alignment": sam,
        "sam": {
            "sha256": sha256(sam_payload),
            "bytes": len(sam_payload),
            "format": "SAM",
            "sort_order": "unsorted",
        },
        "limitations": [
            "Mapped fraction is descriptive execution evidence, not biological quality or reference suitability.",
            "This branch excludes paired/interleaved reads, RNA/splice, long reads, sorting, indexing, BAM/CRAM operations, variant calling, and quantification.",
        ],
    }
    return sam_payload, report


def _safe_output(path: Path, role: str) -> tuple[Path, int, str]:
    root = Path.cwd().resolve(strict=True)
    relative = _relative_inside_root(path, root, role)
    directory_fd = _open_directory_chain(root, relative.parts[:-1], role)
    try:
        try:
            os.stat(relative.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return root / relative, directory_fd, relative.name
        raise fail("invalid-input", "output-exists", f"{role} output already exists")
    except BaseException:
        os.close(directory_fd)
        raise


def _unlink_owned(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(name, dir_fd=directory_fd)
    return True


def _is_owned(name: str, directory_fd: int, identity: tuple[int, int]) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def _rollback_owned(directory_fd: int, identity: tuple[int, int], names: tuple[str, ...]) -> None:
    failures: list[str] = []
    for name in names:
        try:
            if not _unlink_owned(name, directory_fd, identity):
                failures.append(f"{name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{name}:{exc.__class__.__name__}")
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        failures.append(f"directory:{exc.__class__.__name__}")
    if failures:
        raise OSError("publication rollback failed: " + ", ".join(failures))


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("output write made no progress")
        offset += written


def _publish_one(path: Path, payload: bytes, role: str) -> tuple[Path, int, str, tuple[int, int]]:
    target, directory_fd, name = _safe_output(path, role)
    temporary = f".{name}.tmp-{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: tuple[int, int] | None = None
    published = False
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        try:
            os.close(descriptor)
        finally:
            descriptor = -1
        try:
            os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError as exc:
            raise fail("invalid-input", "output-exists", f"{role} output appeared") from exc
        published = True
        if not _is_owned(name, directory_fd, identity):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned(temporary, directory_fd, identity):
            raise OSError("temporary output identity changed after publication")
        os.fsync(directory_fd)
        if not _is_owned(name, directory_fd, identity):
            raise OSError("published output identity changed before completion")
        return target, directory_fd, name, identity
    except BaseException as original:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if identity is not None:
                names = (name, temporary) if published else (temporary,)
                _rollback_owned(directory_fd, identity, names)
        except OSError as rollback_error:
            raise rollback_error from original
        finally:
            os.close(directory_fd)
        raise


def publish_outputs(sam_path: Path, report_path: Path, sam_payload: bytes, report: dict[str, Any]) -> None:
    sam_target = _safe_output(sam_path, "sam-output")
    report_target = _safe_output(report_path, "report-output")
    os.close(sam_target[1])
    os.close(report_target[1])
    if sam_target[0] == report_target[0]:
        raise fail("invalid-input", "output-path-collision", "SAM and report paths must differ")
    report["outputs"] = {
        "sam": {"name": sam_target[0].name, "sha256": sha256(sam_payload), "bytes": len(sam_payload)},
        "report": {"name": report_target[0].name, "format": "JSON"},
    }
    rendered = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    first = _publish_one(sam_path, sam_payload, "sam-output")
    try:
        second = _publish_one(report_path, rendered, "report-output")
    except BaseException as original:
        try:
            _rollback_owned(first[1], first[3], (first[2],))
        except OSError as rollback_error:
            raise rollback_error from original
        finally:
            os.close(first[1])
        raise
    else:
        try:
            os.close(first[1])
        finally:
            os.close(second[1])


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_fake_minimap2(path: Path, version: str = EXPECTED_MINIMAP2_VERSION) -> str:
    script = f'''#!/usr/bin/env python3
import os
import sys

if sys.argv == [sys.argv[0], "--version"]:
    sys.stdout.write("{version}\\n")
    raise SystemExit(0)
expected = ["-a", "-x", "sr", "-t", "1", "--seed", "11", "--secondary=no", "reference.fa", "reads.fastq"]
if sys.argv[1:] != expected or os.getcwd() != os.path.dirname(sys.argv[-1]) and os.path.isabs(sys.argv[-1]):
    raise SystemExit(64)
names = []
with open("reads.fastq", "r", encoding="ascii") as handle:
    lines = handle.read().splitlines()
for index in range(0, len(lines), 4):
    names.append(lines[index][1:].split()[0])
sys.stdout.write("@HD\\tVN:1.6\\tSO:unsorted\\n@SQ\\tSN:ref\\tLN:80\\n")
for index, name in enumerate(names):
    if index == 0:
        sys.stdout.write(f"{{name}}\\t0\\tref\\t1\\t60\\t{{len(lines[index * 4 + 1])}}M\\t*\\t0\\t0\\t{{lines[index * 4 + 1]}}\\t{{lines[index * 4 + 3]}}\\n")
    else:
        sys.stdout.write(f"{{name}}\\t4\\t*\\t0\\t0\\t*\\t*\\t0\\t0\\t{{lines[index * 4 + 1]}}\\t{{lines[index * 4 + 3]}}\\n")
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)
    return sha256(path.read_bytes())


def self_test() -> None:
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        if not condition:
            raise RuntimeError(message)
        checks += 1

    def expect(code: str, action: Any) -> None:
        nonlocal checks
        try:
            action()
        except ContractError as exc:
            if exc.code != code:
                raise RuntimeError(f"expected {code}, received {exc.code}") from exc
        else:
            raise RuntimeError(f"boundary {code} was accepted")
        checks += 1

    def expect_os_error(fragment: str, action: Any) -> None:
        nonlocal checks
        try:
            action()
        except OSError as exc:
            if fragment not in str(exc):
                raise RuntimeError(f"expected OSError containing {fragment!r}, received {exc!r}") from exc
        else:
            raise RuntimeError(f"I/O failure {fragment!r} was accepted")
        checks += 1

    @contextmanager
    def patched_os(name: str, replacement: Any) -> Iterator[None]:
        original = getattr(os, name)
        setattr(os, name, replacement)
        try:
            yield
        finally:
            setattr(os, name, original)

    with tempfile.TemporaryDirectory(prefix="bio02-read-alignment-selftest-") as temporary:
        root = Path(temporary)
        work = root / "work"
        inputs = root / "inputs"
        tools = root / "tools"
        work.mkdir()
        inputs.mkdir()
        tools.mkdir()
        with working_directory(work):
            reference = inputs / "reference.fa"
            reads = inputs / "reads.fastq"
            executable = tools / "fake-minimap2"
            reference.write_text(">ref\n" + "ACGT" * 20 + "\n", encoding="ascii")
            reads.write_text(
                "@mapped\n" + "ACGT" * 10 + "\n+\n" + "I" * 40 + "\n"
                "@unmapped\n" + "TGCA" * 10 + "\n+\n" + "I" * 40 + "\n",
                encoding="ascii",
            )
            digest = _write_fake_minimap2(executable)
            linked_reference = work / "linked-reference.fa"
            linked_reference.symlink_to(reference)
            linked_input_parent = work / "linked-input-parent"
            linked_input_parent.symlink_to(inputs, target_is_directory=True)
            linked_executable = work / "minimap2"
            linked_executable.symlink_to(executable)
            arguments = {
                "reference_path": linked_reference,
                "reads_path": linked_input_parent / "reads.fastq",
                "executable_path": linked_executable,
                "expected_executable_digest": None,
                "declared_single_end_short_genomic_dna": True,
            }
            first_sam, first = analyze(**arguments)
            second_sam, second = analyze(**{**arguments, "expected_executable_digest": digest})
            if first_sam != second_sam or first != second:
                raise RuntimeError("repeatability check failed")
            if first["alignment"]["mapped_primary_reads"] != 1 or first["alignment"]["unmapped_primary_reads"] != 1:
                raise RuntimeError("mapping count reconciliation failed")
            if first["tool"]["executable_sha256"] != digest:
                raise RuntimeError("automatic executable fingerprinting failed")
            checks += 3

            parsed_reference = parse_fasta(reference.read_bytes())
            parsed_reads = parse_fastq(reads.read_bytes())
            expect(
                "sam-reference-dictionary-mismatch",
                lambda: parse_sam(first_sam.replace(b"@SQ\tSN:ref\tLN:80\n", b""), parsed_reads, parsed_reference),
            )
            expect(
                "unknown-sam-reference",
                lambda: parse_sam(first_sam.replace(b"\tref\t1\t60\t40M\t", b"\tother\t1\t60\t40M\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "unexpected-sam-flags",
                lambda: parse_sam(first_sam.replace(b"mapped\t0\t", b"mapped\t64\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "secondary-sam-record-refused",
                lambda: parse_sam(first_sam.replace(b"mapped\t0\t", b"mapped\t256\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "invalid-sam-cigar",
                lambda: parse_sam(first_sam.replace(b"\t40M\t", b"\tNOT_A_CIGAR\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "sam-read-evidence-mismatch",
                lambda: parse_sam(first_sam.replace(b"ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT", b"TCGTACGTACGTACGTACGTACGTACGTACGTACGTACGT", 1), parsed_reads, parsed_reference),
            )
            expect(
                "unsupported-sam-cigar-operation",
                lambda: parse_sam(first_sam.replace(b"\t40M\t", b"\t10M1H30M\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "invalid-sam-cigar-clipping",
                lambda: parse_sam(first_sam.replace(b"\t40M\t", b"\t15M10S15M\t", 1), parsed_reads, parsed_reference),
            )
            expect(
                "sam-cigar-without-alignment",
                lambda: parse_sam(first_sam.replace(b"\t40M\t", b"\t1D40S\t", 1), parsed_reads, parsed_reference),
            )

            sam_output = work / "out.sam"
            report_output = work / "out.json"
            publish_outputs(sam_output, report_output, first_sam, first)
            published = json.loads(report_output.read_text(encoding="utf-8"))
            if sam_output.read_bytes() != first_sam or published["sam"]["sha256"] != sha256(first_sam):
                raise RuntimeError("published artifacts differ")
            checks += 1
            expect("output-exists", lambda: publish_outputs(sam_output, work / "other.json", first_sam, first))

            zero_sam = work / "zero.sam"
            zero_report = work / "zero.json"
            with patched_os("write", lambda _descriptor, _payload: 0):
                expect_os_error("no progress", lambda: publish_outputs(zero_sam, zero_report, first_sam, first))
            check(not zero_sam.exists() and not zero_report.exists(), "zero-write publication left a final output")
            check(not list(work.glob(".zero.*.tmp-*")), "zero-write publication left a temporary output")

            original_write = os.write

            def short_write(descriptor: int, payload: bytes) -> int:
                return original_write(descriptor, payload[:max(1, len(payload) // 3)])

            short_sam = work / "short.sam"
            short_report = work / "short.json"
            with patched_os("write", short_write):
                publish_outputs(short_sam, short_report, first_sam, first)
            check(short_sam.read_bytes() == first_sam, "short writes truncated the SAM output")
            check(json.loads(short_report.read_text(encoding="utf-8"))["sam"]["sha256"] == sha256(first_sam), "short writes truncated the report output")

            unlink_sam = work / "unlink.sam"
            unlink_report = work / "unlink.json"
            original_unlink = os.unlink
            unlink_failed = False

            def fail_postlink_unlink(path: str, *args: Any, **kwargs: Any) -> None:
                nonlocal unlink_failed
                if not unlink_failed and path.startswith(".unlink.json.tmp-"):
                    unlink_failed = True
                    raise OSError("injected post-link temporary unlink failure")
                original_unlink(path, *args, **kwargs)

            with patched_os("unlink", fail_postlink_unlink):
                expect_os_error(
                    "injected post-link",
                    lambda: publish_outputs(unlink_sam, unlink_report, first_sam, first),
                )
            check(not unlink_sam.exists() and not unlink_report.exists(), "post-link unlink failure left a final output")
            check(not list(work.glob(".unlink.*.tmp-*")), "post-link unlink failure left a temporary output")

            fsync_sam = work / "fsync.sam"
            fsync_report = work / "fsync.json"
            original_fsync = os.fsync
            directory_fsync_calls = 0

            def fail_second_postlink_fsync(descriptor: int) -> None:
                nonlocal directory_fsync_calls
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    directory_fsync_calls += 1
                    if directory_fsync_calls == 2:
                        raise OSError("injected post-link directory fsync failure")
                original_fsync(descriptor)

            with patched_os("fsync", fail_second_postlink_fsync):
                expect_os_error(
                    "injected post-link",
                    lambda: publish_outputs(fsync_sam, fsync_report, first_sam, first),
                )
            check(not fsync_sam.exists() and not fsync_report.exists(), "post-link fsync failure left a final output")
            check(not list(work.glob(".fsync.*.tmp-*")), "post-link fsync failure left a temporary output")

            race_sam = work / "race.sam"
            race_report = work / "race.json"
            original_link = os.link

            def insert_competing_report(source: str, destination: str, *args: Any, **kwargs: Any) -> None:
                if destination == race_report.name:
                    competitor = os.open(
                        destination,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=kwargs["dst_dir_fd"],
                    )
                    try:
                        _write_all(competitor, b"competitor\n")
                        os.fsync(competitor)
                    finally:
                        os.close(competitor)
                original_link(source, destination, *args, **kwargs)

            with patched_os("link", insert_competing_report):
                expect("output-exists", lambda: publish_outputs(race_sam, race_report, first_sam, first))
            check(not race_sam.exists(), "report publication race left the owned SAM output")
            check(race_report.read_bytes() == b"competitor\n", "publication overwrote a competing report")
            check(not list(work.glob(".race.*.tmp-*")), "output race left an owned temporary output")

            identity_sam = work / "identity.sam"
            identity_report = work / "identity.json"

            def replace_report_temporary(source: str, destination: str, *args: Any, **kwargs: Any) -> None:
                original_link(source, destination, *args, **kwargs)
                if destination != identity_report.name:
                    return
                original_unlink(source, dir_fd=kwargs["src_dir_fd"])
                replacement = os.open(
                    source,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=kwargs["src_dir_fd"],
                )
                try:
                    _write_all(replacement, b"replacement\n")
                    os.fsync(replacement)
                finally:
                    os.close(replacement)

            with patched_os("link", replace_report_temporary):
                expect_os_error(
                    "publication rollback failed",
                    lambda: publish_outputs(identity_sam, identity_report, first_sam, first),
                )
            replacements = list(work.glob(".identity.json.tmp-*"))
            check(not identity_sam.exists() and not identity_report.exists(), "identity mismatch rollback left an owned final output")
            check(
                len(replacements) == 1 and replacements[0].read_bytes() == b"replacement\n",
                "identity mismatch rollback removed an unowned temporary output",
            )
            replacements[0].unlink()

            final_identity_sam = work / "final-identity.sam"
            final_identity_report = work / "final-identity.json"
            final_identity_swapped = False

            def replace_report_during_cleanup(path: str, *args: Any, **kwargs: Any) -> None:
                nonlocal final_identity_swapped
                if not final_identity_swapped and path.startswith(".final-identity.json.tmp-"):
                    final_identity_swapped = True
                    original_unlink(final_identity_report.name, dir_fd=kwargs["dir_fd"])
                    replacement = os.open(
                        final_identity_report.name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=kwargs["dir_fd"],
                    )
                    try:
                        _write_all(replacement, b"competitor\n")
                        os.fsync(replacement)
                    finally:
                        os.close(replacement)
                original_unlink(path, *args, **kwargs)

            with patched_os("unlink", replace_report_during_cleanup):
                expect_os_error(
                    "publication rollback failed",
                    lambda: publish_outputs(final_identity_sam, final_identity_report, first_sam, first),
                )
            check(not final_identity_sam.exists(), "report identity failure left the owned SAM output")
            check(
                final_identity_report.read_bytes() == b"competitor\n",
                "identity check removed a replacement report output",
            )
            check(not list(work.glob(".final-identity.*.tmp-*")), "identity check left an owned temporary output")
            final_identity_report.unlink()
            expect("missing-assay-declaration", lambda: analyze(**{**arguments, "declared_single_end_short_genomic_dna": False}))
            expect("minimap2-digest-mismatch", lambda: analyze(**{**arguments, "expected_executable_digest": "0" * 64}))
            expect("minimap2-unavailable", lambda: analyze(**{**arguments, "executable_path": work / "missing"}))

            wrong = tools / "wrong-minimap2"
            wrong_digest = _write_fake_minimap2(wrong, "2.30-r1287")
            expect("unsupported-minimap2-version", lambda: analyze(**{**arguments, "executable_path": wrong, "expected_executable_digest": wrong_digest}))

            paired = inputs / "paired.fastq"
            paired.write_text(reads.read_text(encoding="ascii").replace("@mapped", "@mapped/1"), encoding="ascii")
            expect("paired-read-name-refused", lambda: analyze(**{**arguments, "reads_path": paired}))
            invalid = inputs / "invalid.fastq"
            invalid.write_text("@r\nACGT\n+\nIII\n", encoding="ascii")
            expect("invalid-read-quality", lambda: analyze(**{**arguments, "reads_path": invalid}))
            plus_mismatch = inputs / "plus-mismatch.fastq"
            plus_mismatch.write_text("@r\n" + "ACGT" * 10 + "\n+other\n" + "I" * 40 + "\n", encoding="ascii")
            expect("fastq-plus-identifier-mismatch", lambda: analyze(**{**arguments, "reads_path": plus_mismatch}))

            broken_link = work / "broken.fastq"
            broken_link.symlink_to(inputs / "missing.fastq")
            expect("unreadable-reads", lambda: analyze(**{**arguments, "reads_path": broken_link}))
            parent = work / "parent"
            parent.mkdir()
            linked_parent = work / "linked-parent"
            linked_parent.symlink_to(parent, target_is_directory=True)
            expect("unsafe-sam-output-parent", lambda: publish_outputs(linked_parent / "x.sam", work / "x.json", first_sam, first))
            expect("invalid-sam-output-path", lambda: publish_outputs(Path("..") / "x.sam", work / "x.json", first_sam, first))
    print(json.dumps({"checks": checks, "real_minimap2_runtime": "not-evaluated", "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--reference", type=Path)
    result.add_argument("--reads", type=Path)
    result.add_argument("--minimap2", type=Path)
    result.add_argument("--minimap2-sha256")
    result.add_argument("--output-sam", type=Path)
    result.add_argument("--output-report", type=Path)
    result.add_argument("--declared-single-end-short-genomic-dna", action="store_true")
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    required = ("reference", "reads", "minimap2", "output_sam", "output_report")
    missing = [f"--{name.replace('_', '-')}" for name in required if getattr(arguments, name) is None]
    if missing:
        print(json.dumps({
            "analysis_performed": False,
            "code": "missing-required-input",
            "missing": missing,
            "status": "needs-decision",
        }, sort_keys=True), file=sys.stderr)
        return 2
    try:
        sam_target, sam_fd, _ = _safe_output(arguments.output_sam, "sam-output")
        report_target, report_fd, _ = _safe_output(arguments.output_report, "report-output")
        os.close(sam_fd)
        os.close(report_fd)
        if sam_target == report_target:
            raise fail("invalid-input", "output-path-collision", "SAM and report paths must differ")
        sam_payload, report = analyze(
            reference_path=arguments.reference,
            reads_path=arguments.reads,
            executable_path=arguments.minimap2,
            expected_executable_digest=arguments.minimap2_sha256,
            declared_single_end_short_genomic_dna=arguments.declared_single_end_short_genomic_dna,
        )
        publish_outputs(arguments.output_sam, arguments.output_report, sam_payload, report)
        print(json.dumps({
            "analysis_performed": True,
            "mapped_primary_reads": report["alignment"]["mapped_primary_reads"],
            "outputs_created": [sam_target.name, report_target.name],
            "status": "completed",
            "total_primary_reads": report["alignment"]["primary_records"],
            "unmapped_primary_reads": report["alignment"]["unmapped_primary_reads"],
        }, sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({
            "analysis_performed": False,
            "code": exc.code,
            "message": exc.message,
            "status": exc.status,
        }, sort_keys=True), file=sys.stderr)
        return 3 if exc.status == "needs-tool" else 2
    except (OSError, UnicodeError, ValueError):
        print(json.dumps({
            "analysis_performed": False,
            "code": "local-io-failure",
            "message": "local I/O failed closed",
            "status": "io-error",
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
