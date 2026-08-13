#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Count one bounded single-end SAM against gene exon unions in an exact GTF."""

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
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


VERSION = "0.8.0"
MAX_SAM_BYTES = 32 * 1024 * 1024
MAX_GTF_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_ALIGNMENT_RECORDS = 100_000
MAX_EXONS = 100_000
MAX_GENES = 50_000
MAX_ID_CHARS = 256
MAX_OVERLAP_COMPARISONS = 5_000_000
CIGAR = re.compile(rb"(?:[1-9][0-9]*[MIDNSHP=X])+\Z")
CIGAR_PART = re.compile(rb"([1-9][0-9]*)([MIDNSHP=X])")
SAFE_TOKEN = re.compile(r"[^\x00-\x20\x7f]+\Z")
PAIRED_BITS = 0x1 | 0x2 | 0x8 | 0x20 | 0x40 | 0x80
KNOWN_FLAG_BITS = 0xFFF
STRANDEDNESS = ("unstranded", "forward", "reverse")


class ContractError(Exception):
    """Structured fail-closed result safe to expose."""

    def __init__(self, status: str, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def fail(status: str, code: str, message: str) -> ContractError:
    return ContractError(status, code, message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_token(value: str, role: str) -> str:
    if (
        not value
        or len(value) > MAX_ID_CHARS
        or not SAFE_TOKEN.fullmatch(value)
        or value != value.strip()
    ):
        raise fail("invalid-input", f"invalid-{role}", f"{role} is empty or unsafe")
    return value


def validate_label(value: str, role: str) -> str:
    if (
        not value
        or len(value) > MAX_ID_CHARS
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise fail("invalid-input", f"invalid-{role}", f"{role} is empty or unsafe")
    return value


def _relative_inside_root(path: Path, root: Path, role: str) -> Path:
    raw = os.fspath(path)
    if not raw or "\x00" in raw or ".." in path.parts:
        raise fail("invalid-input", f"invalid-{role}-path", f"{role} path is invalid")
    supplied = Path(os.path.abspath(path))
    lexical_cwd = Path(os.getcwd())
    candidates = [lexical_cwd, root]
    if os.fspath(lexical_cwd).startswith("/private/"):
        candidates.append(Path(os.fspath(lexical_cwd)[8:]))
    if os.fspath(root).startswith("/private/"):
        candidates.append(Path(os.fspath(root)[8:]))
    relative: Path | None = None
    for candidate in candidates:
        try:
            relative = supplied.relative_to(candidate)
            break
        except ValueError:
            continue
    if relative is None or not relative.parts:
        raise fail("invalid-input", f"{role}-outside-cwd", f"{role} must remain inside cwd")
    return relative


def _open_directory_chain(root: Path, parts: tuple[str, ...], role: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(root, flags)
        for part in parts:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise fail("invalid-input", f"unsafe-{role}-parent", f"{role} parent is unsafe") from exc


def read_input(path: Path, role: str, limit: int) -> bytes:
    root = Path.cwd().resolve(strict=True)
    if Path.cwd().is_symlink() or not root.is_dir():
        raise fail("invalid-input", "unsafe-cwd", "cwd must be a real directory")
    relative = _relative_inside_root(path, root, role)
    directory_fd = _open_directory_chain(root, relative.parts[:-1], role)
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(relative.name, flags, dir_fd=directory_fd)
        except OSError as exc:
            raise fail("invalid-input", f"unreadable-{role}", f"{role} is unavailable or unsafe") from exc
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise fail("invalid-input", f"{role}-not-regular", f"{role} must be a regular file")
        if opened.st_size > limit:
            raise fail("needs-tool", f"{role}-too-large", f"{role} exceeds the preview byte limit")
        payload = bytearray()
        while len(payload) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        path_after = os.stat(relative.name, dir_fd=directory_fd, follow_symlinks=False)
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) > limit:
            raise fail("needs-tool", f"{role}-too-large", f"{role} exceeds the preview byte limit")
        if any(getattr(opened, key) != getattr(after, key) for key in stable):
            raise fail("invalid-input", f"{role}-changed", f"{role} changed while reading")
        if any(getattr(after, key) != getattr(path_after, key) for key in stable):
            raise fail("invalid-input", f"{role}-changed", f"{role} changed while reading")
        return bytes(payload)
    except ContractError:
        raise
    except OSError as exc:
        raise fail("invalid-input", f"unreadable-{role}", f"{role} could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


def ascii_lines(payload: bytes, role: str) -> list[bytes]:
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


def parse_uint(raw: bytes, role: str, maximum: int) -> int:
    if not raw or not raw.isdigit():
        raise fail("invalid-input", f"invalid-{role}", f"{role} must be an unsigned integer")
    significant = raw.lstrip(b"0") or b"0"
    ceiling = str(maximum).encode("ascii")
    if len(significant) > len(ceiling) or (
        len(significant) == len(ceiling) and significant > ceiling
    ):
        raise fail("invalid-input", f"invalid-{role}", f"{role} exceeds its allowed range")
    return int(significant)


def parse_sq(line: bytes) -> tuple[str, int]:
    tags: dict[bytes, bytes] = {}
    for token in line.split(b"\t")[1:]:
        if b":" not in token:
            raise fail("invalid-input", "malformed-sam-sq", "SAM @SQ fields must be tagged")
        key, value = token.split(b":", 1)
        if key in tags:
            raise fail("invalid-input", "duplicate-sam-sq-tag", "SAM @SQ tags must be unique")
        tags[key] = value
    if b"SN" not in tags or b"LN" not in tags:
        raise fail("invalid-input", "incomplete-sam-sq", "SAM @SQ requires SN and LN")
    try:
        name = tags[b"SN"].decode("ascii")
    except UnicodeDecodeError as exc:
        raise fail("invalid-input", "invalid-sam-reference-name", "SAM reference name must be ASCII") from exc
    validate_token(name, "sam-reference-name")
    length = parse_uint(tags[b"LN"], "sam-reference-length", 2**63 - 1)
    if length == 0:
        raise fail("invalid-input", "invalid-sam-reference-length", "SAM reference length must be positive")
    return name, length


def parse_rg_header(line: bytes) -> tuple[str, str | None]:
    tags: dict[bytes, bytes] = {}
    for token in line.split(b"\t")[1:]:
        if b":" not in token:
            raise fail("invalid-input", "malformed-sam-rg", "SAM @RG fields must be tagged")
        key, value = token.split(b":", 1)
        if key in tags:
            raise fail("invalid-input", "duplicate-sam-rg-tag", "SAM @RG tags must be unique")
        tags[key] = value
    if b"ID" not in tags:
        raise fail("invalid-input", "incomplete-sam-rg", "SAM @RG requires ID")
    try:
        identifier = validate_token(tags[b"ID"].decode("ascii"), "sam-read-group-id")
        sample = tags[b"SM"].decode("ascii") if b"SM" in tags else None
    except UnicodeDecodeError as exc:
        raise fail("invalid-input", "invalid-sam-rg", "SAM read-group identifiers must be ASCII") from exc
    if sample is not None:
        validate_label(sample, "sam-sample-id")
    return identifier, sample


def parse_cigar(raw: bytes, position: int, reference_length: int) -> list[tuple[int, int]]:
    if not CIGAR.fullmatch(raw):
        raise fail("invalid-input", "invalid-sam-cigar", "mapped SAM records require a valid CIGAR")
    operations = [
        (parse_uint(match.group(1), "sam-cigar-operation-length", 2**31 - 1), match.group(2))
        for match in CIGAR_PART.finditer(raw)
    ]
    aligned_indexes = [index for index, (_, operation) in enumerate(operations) if operation not in {b"H", b"S"}]
    if not aligned_indexes or any(
        operation == b"H" and index not in {0, len(operations) - 1}
        or operation == b"S" and aligned_indexes[0] < index < aligned_indexes[-1]
        for index, (_, operation) in enumerate(operations)
    ):
        raise fail("invalid-input", "invalid-sam-cigar-clipping", "SAM clipping must be terminal")
    blocks: list[tuple[int, int]] = []
    cursor = position
    reference_bases = 0
    aligned_bases = 0
    for length, operation in operations:
        if operation in {b"M", b"=", b"X"}:
            blocks.append((cursor, cursor + length - 1))
            cursor += length
            reference_bases += length
            aligned_bases += length
        elif operation in {b"D", b"N"}:
            cursor += length
            reference_bases += length
        elif operation in {b"I", b"S", b"H", b"P"}:
            continue
    if aligned_bases == 0 or reference_bases == 0:
        raise fail("invalid-input", "sam-cigar-without-alignment", "CIGAR has no aligned reference bases")
    if position + reference_bases - 1 > reference_length:
        raise fail("invalid-input", "sam-reference-span-invalid", "alignment exceeds its @SQ reference")
    return blocks


def parse_nh(optional_fields: list[bytes]) -> int | None:
    nh: int | None = None
    for field in optional_fields:
        if not field.startswith(b"NH:"):
            continue
        if nh is not None or not field.startswith(b"NH:i:"):
            raise fail("invalid-input", "invalid-sam-nh-tag", "SAM NH must be one positive integer tag")
        nh = parse_uint(field[5:], "sam-nh", 2**31 - 1)
        if nh == 0:
            raise fail("invalid-input", "invalid-sam-nh-tag", "SAM NH must be positive")
    return nh


def parse_record_rg(optional_fields: list[bytes], read_groups: dict[str, str | None]) -> None:
    observed: str | None = None
    for field in optional_fields:
        if not field.startswith(b"RG:"):
            continue
        if observed is not None or not field.startswith(b"RG:Z:"):
            raise fail("invalid-input", "invalid-sam-rg-tag", "SAM RG must be one string tag")
        try:
            observed = validate_token(field[5:].decode("ascii"), "sam-read-group-id")
        except UnicodeDecodeError as exc:
            raise fail("invalid-input", "invalid-sam-rg-tag", "SAM RG tag must be ASCII") from exc
    if observed is not None and observed not in read_groups:
        raise fail("invalid-input", "unknown-sam-read-group", "primary SAM record references an unknown @RG ID")


def parse_sam(payload: bytes) -> dict[str, Any]:
    dictionary: dict[str, int] = {}
    read_groups: dict[str, str | None] = {}
    records: list[dict[str, Any]] = []
    primary_names: set[str] = set()
    header_lines = 0
    secondary = 0
    supplementary = 0
    alignment_records = 0
    saw_record = False
    for line_number, line in enumerate(ascii_lines(payload, "sam"), start=1):
        if line.startswith(b"@"):
            if saw_record:
                raise fail("invalid-input", "sam-header-after-record", "SAM headers must precede records")
            header_lines += 1
            if line.startswith(b"@SQ\t"):
                name, length = parse_sq(line)
                if name in dictionary:
                    raise fail("invalid-input", "duplicate-sam-reference", "SAM @SQ names must be unique")
                dictionary[name] = length
            elif line.startswith(b"@RG\t"):
                identifier, sample = parse_rg_header(line)
                if identifier in read_groups:
                    raise fail("invalid-input", "duplicate-sam-read-group", "SAM @RG IDs must be unique")
                read_groups[identifier] = sample
            elif not line.startswith((b"@HD\t", b"@PG\t", b"@CO\t")):
                raise fail("invalid-input", "unsupported-sam-header", "SAM header record type is unsupported")
            continue
        saw_record = True
        alignment_records += 1
        if alignment_records > MAX_ALIGNMENT_RECORDS:
            raise fail("needs-tool", "too-many-sam-records", "SAM exceeds the preview record limit")
        fields = line.split(b"\t")
        if len(fields) < 11:
            raise fail("invalid-input", "short-sam-record", f"SAM line {line_number} has fewer than 11 fields")
        try:
            qname = fields[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise fail("invalid-input", "invalid-sam-read-name", "SAM read name must be ASCII") from exc
        validate_token(qname, "sam-read-name")
        flag = parse_uint(fields[1], "sam-flag", 65535)
        if flag & ~KNOWN_FLAG_BITS:
            raise fail("invalid-input", "unknown-sam-flag-bits", "SAM FLAG uses unknown bits")
        if flag & PAIRED_BITS:
            raise fail("needs-tool", "paired-sam-out-of-scope", "paired-end or mate-aware SAM is outside this preview")
        if flag & 0x100:
            secondary += 1
            continue
        if flag & 0x800:
            supplementary += 1
            continue
        if qname in primary_names:
            raise fail("invalid-input", "duplicate-primary-read-name", "primary single-end read names must be unique")
        primary_names.add(qname)
        parse_record_rg(fields[11:], read_groups)

        mapq = parse_uint(fields[4], "sam-mapq", 255)
        if flag & 0x4:
            if fields[2] != b"*" or fields[3] != b"0" or fields[5] != b"*":
                raise fail("invalid-input", "invalid-unmapped-sam-record", "unmapped record coordinates must be absent")
            records.append({
                "category": "unmapped",
                "duplicate": bool(flag & 0x400),
                "qcfail": bool(flag & 0x200),
                "qname": qname,
            })
            continue
        try:
            reference = fields[2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise fail("invalid-input", "invalid-sam-reference-name", "SAM reference name must be ASCII") from exc
        if reference not in dictionary:
            raise fail("invalid-input", "unknown-sam-reference", "mapped record reference is absent from @SQ")
        position = parse_uint(fields[3], "sam-position", dictionary[reference])
        if position == 0:
            raise fail("invalid-input", "invalid-sam-position", "mapped SAM position must be positive")
        if fields[6] != b"*" or fields[7] != b"0" or fields[8] != b"0":
            raise fail("needs-tool", "mate-fields-out-of-scope", "single-end SAM mate fields must be empty")
        blocks = parse_cigar(fields[5], position, dictionary[reference])
        records.append({
            "blocks": blocks,
            "category": "mapped",
            "duplicate": bool(flag & 0x400),
            "mapq": mapq,
            "nh": parse_nh(fields[11:]),
            "qcfail": bool(flag & 0x200),
            "qname": qname,
            "reference": reference,
            "reverse": bool(flag & 0x10),
        })
    if not dictionary:
        raise fail("invalid-input", "missing-sam-reference-dictionary", "SAM requires at least one @SQ header")
    if not records:
        raise fail("invalid-input", "no-primary-sam-records", "SAM requires at least one primary record")
    return {
        "alignment_records": alignment_records,
        "dictionary": dictionary,
        "header_lines": header_lines,
        "primary_records": len(records),
        "read_group_count": len(read_groups),
        "read_group_sample_ids": sorted({sample for sample in read_groups.values() if sample is not None}),
        "records": records,
        "secondary_records_ignored": secondary,
        "supplementary_records_ignored": supplementary,
    }


def parse_gene_id(attributes: str) -> str:
    matches: list[str] = []
    for item in attributes.split(";"):
        item = item.strip()
        if not item:
            continue
        match = re.fullmatch(r'gene_id\s+"([^"]+)"', item)
        if match:
            matches.append(match.group(1))
    if len(matches) != 1:
        raise fail("invalid-input", "missing-or-duplicate-gtf-gene-id", "each exon requires one exact gene_id")
    return validate_token(matches[0], "gtf-gene-id")


def parse_gtf(payload: bytes, dictionary: dict[str, int]) -> dict[str, Any]:
    if b"\x00" in payload:
        raise fail("invalid-input", "invalid-gtf", "GTF contains a NUL byte")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise fail("invalid-input", "non-utf8-gtf", "GTF must be UTF-8") from exc
    exons_by_contig: dict[str, list[tuple[int, int, str, str]]] = {}
    genes: dict[str, dict[str, Any]] = {}
    exon_count = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise fail("invalid-input", "oversized-gtf-line", "GTF has an oversized line")
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 9:
            raise fail("invalid-input", "malformed-gtf-row", f"GTF line {line_number} must have nine columns")
        if fields[2] != "exon":
            continue
        contig = validate_token(fields[0], "gtf-contig")
        if contig not in dictionary:
            raise fail("invalid-input", "gtf-contig-not-in-sam", "GTF exon contig is absent from SAM @SQ")
        if not re.fullmatch(r"[0-9]+", fields[3]) or not re.fullmatch(r"[0-9]+", fields[4]):
            raise fail("invalid-input", "invalid-gtf-coordinate", "GTF exon coordinates must be positive integers")
        start = parse_uint(fields[3].encode("ascii"), "gtf-start", dictionary[contig])
        end = parse_uint(fields[4].encode("ascii"), "gtf-end", dictionary[contig])
        if start < 1 or end < start or end > dictionary[contig]:
            raise fail("invalid-input", "gtf-coordinate-out-of-range", "GTF exon exceeds the SAM reference dictionary")
        strand = fields[6]
        if strand not in {"+", "-"}:
            raise fail("invalid-input", "invalid-gtf-exon-strand", "GTF exons require + or - strand")
        gene_id = parse_gene_id(fields[8])
        existing = genes.get(gene_id)
        if existing is not None and (existing["contig"], existing["strand"]) != (contig, strand):
            raise fail("invalid-input", "inconsistent-gtf-gene-locus", "one gene_id spans multiple contigs or strands")
        if existing is None:
            if len(genes) >= MAX_GENES:
                raise fail("needs-tool", "too-many-gtf-genes", "GTF exceeds the preview gene limit")
            existing = {"contig": contig, "exon_count": 0, "strand": strand}
            genes[gene_id] = existing
        existing["exon_count"] += 1
        exon_count += 1
        if exon_count > MAX_EXONS:
            raise fail("needs-tool", "too-many-gtf-exons", "GTF exceeds the preview exon limit")
        exons_by_contig.setdefault(contig, []).append((start, end, gene_id, strand))
    if not genes:
        raise fail("invalid-input", "no-gtf-exons", "GTF requires at least one exon with gene_id")
    for exons in exons_by_contig.values():
        exons.sort()
    return {"exon_count": exon_count, "exons_by_contig": exons_by_contig, "genes": genes}


def strand_compatible(read_strand: str, gene_strand: str, strandedness: str) -> bool:
    if strandedness == "unstranded":
        return True
    if strandedness == "forward":
        return read_strand == gene_strand
    return read_strand != gene_strand


def overlapping_genes(
    blocks: list[tuple[int, int]],
    exons: list[tuple[int, int, str, str]],
    read_strand: str,
    strandedness: str,
) -> tuple[set[str], set[str]]:
    all_genes: set[str] = set()
    compatible: set[str] = set()
    # ponytail: bounded linear scan; a batch-scale interval index belongs in a separate adapter.
    for block_start, block_end in blocks:
        for exon_start, exon_end, gene_id, gene_strand in exons:
            if exon_start > block_end:
                break
            if exon_end < block_start:
                continue
            all_genes.add(gene_id)
            if strand_compatible(read_strand, gene_strand, strandedness):
                compatible.add(gene_id)
    return all_genes, compatible


def analyze(
    sam_payload: bytes,
    gtf_payload: bytes,
    *,
    sample_id: str,
    strandedness: str,
    min_mapq: int,
) -> dict[str, Any]:
    validate_label(sample_id, "sample-id")
    if strandedness not in STRANDEDNESS:
        raise fail("invalid-input", "invalid-strandedness", "strandedness must be explicitly supported")
    if not 0 <= min_mapq <= 255:
        raise fail("invalid-input", "invalid-min-mapq", "minimum MAPQ must be from 0 through 255")
    sam = parse_sam(sam_payload)
    if len(sam["read_group_sample_ids"]) > 1:
        raise fail("needs-tool", "multiple-sam-samples-out-of-scope", "SAM @RG headers declare multiple samples")
    if sam["read_group_sample_ids"] and sam["read_group_sample_ids"][0] != sample_id:
        raise fail("invalid-input", "sample-id-header-mismatch", "sample ID differs from the sole SAM @RG SM value")
    gtf = parse_gtf(gtf_payload, sam["dictionary"])
    comparisons = sum(
        len(record["blocks"]) * len(gtf["exons_by_contig"].get(record["reference"], []))
        for record in sam["records"]
        if record["category"] == "mapped"
    )
    if comparisons > MAX_OVERLAP_COMPARISONS:
        raise fail("needs-tool", "overlap-work-too-large", "bounded linear overlap work exceeds the preview limit")

    summary = {
        "ambiguous": 0,
        "assigned": 0,
        "low_mapq": 0,
        "multimapped": 0,
        "no_feature": 0,
        "qc_fail": 0,
        "unmapped": 0,
        "wrong_strand": 0,
    }
    counts = {gene_id: 0 for gene_id in gtf["genes"]}
    duplicate_records_observed = 0
    mapped_records_without_nh = 0
    for record in sam["records"]:
        if record["duplicate"]:
            duplicate_records_observed += 1
        if record["category"] == "mapped" and record["nh"] is None:
            mapped_records_without_nh += 1
        if record["qcfail"]:
            summary["qc_fail"] += 1
            continue
        if record["category"] == "unmapped":
            summary["unmapped"] += 1
            continue
        if record["mapq"] < min_mapq:
            summary["low_mapq"] += 1
            continue
        if record["nh"] is not None and record["nh"] > 1:
            summary["multimapped"] += 1
            continue
        read_strand = "-" if record["reverse"] else "+"
        all_genes, compatible = overlapping_genes(
            record["blocks"],
            gtf["exons_by_contig"].get(record["reference"], []),
            read_strand,
            strandedness,
        )
        if not compatible:
            summary["wrong_strand" if all_genes else "no_feature"] += 1
        elif len(compatible) > 1:
            summary["ambiguous"] += 1
        else:
            gene_id = next(iter(compatible))
            counts[gene_id] += 1
            summary["assigned"] += 1
    if sum(summary.values()) != sam["primary_records"]:
        raise RuntimeError("internal primary-record reconciliation failed")

    gene_counts = [
        {
            "contig": gtf["genes"][gene_id]["contig"],
            "count": counts[gene_id],
            "exon_count": gtf["genes"][gene_id]["exon_count"],
            "gene_id": gene_id,
            "strand": gtf["genes"][gene_id]["strand"],
        }
        for gene_id in sorted(counts)
    ]
    return {
        "adapter": {"name": "count_gene_alignments", "version": VERSION},
        "analysis_performed": True,
        "assignment_contract": {
            "duplicate_primary_records": "duplicate-flag-alone-does-not-exclude; observed-count-reported",
            "feature": "exon",
            "identity": "gene_id",
            "minimum_mapq": min_mapq,
            "missing_nh": "accepted-by-mapq-and-reported",
            "nh_greater_than_one": "unassigned-multimapped",
            "secondary_and_supplementary": "ignored-and-reported",
            "strandedness": strandedness,
        },
        "assignment_summary": {
            **summary,
            "duplicate_primary_records_observed": duplicate_records_observed,
            "mapped_primary_records_without_nh": mapped_records_without_nh,
            "primary_records": sam["primary_records"],
        },
        "counts": gene_counts,
        "inputs": {
            "gtf": {
                "bytes": len(gtf_payload),
                "exon_count": gtf["exon_count"],
                "gene_count": len(gtf["genes"]),
                "sha256": sha256(gtf_payload),
            },
            "sam": {
                "alignment_records": sam["alignment_records"],
                "bytes": len(sam_payload),
                "header_lines": sam["header_lines"],
                "primary_records": sam["primary_records"],
                "read_group_count": sam["read_group_count"],
                "read_group_sample_ids": sam["read_group_sample_ids"],
                "reference_sequence_count": len(sam["dictionary"]),
                "secondary_records_ignored": sam["secondary_records_ignored"],
                "sha256": sha256(sam_payload),
                "supplementary_records_ignored": sam["supplementary_records_ignored"],
            },
        },
        "limitations": [
            "This preview counts one small primary single-end SAM sample; paired fragments and batches are excluded.",
            "Counts are technical assignments, not normalization, differential expression, transcript abundance, or biological interpretation.",
            "Missing NH tags are reported and accepted by MAPQ; aligner-specific MAPQ semantics remain a researcher review boundary.",
        ],
        "sample_id": sample_id,
        "schema_version": "1.0",
        "status": "completed",
    }


def _safe_output(path: Path) -> tuple[Path, int, str]:
    root = Path.cwd().resolve(strict=True)
    relative = _relative_inside_root(path, root, "output")
    directory_fd = _open_directory_chain(root, relative.parts[:-1], "output")
    try:
        try:
            os.stat(relative.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return root / relative, directory_fd, relative.name
        raise fail("invalid-input", "output-exists", "output already exists")
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


def write_new(path: Path, payload: bytes) -> Path:
    target, directory_fd, name = _safe_output(path)
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
            raise fail("invalid-input", "output-exists", "output appeared during publication") from exc
        published = True
        if not _is_owned(name, directory_fd, identity):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned(temporary, directory_fd, identity):
            raise OSError("temporary output identity changed after publication")
        os.fsync(directory_fd)
        if not _is_owned(name, directory_fd, identity):
            raise OSError("published output identity changed before completion")
        return target
    except BaseException as original:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            names = (name, temporary) if published else (temporary,)
            try:
                _rollback_owned(directory_fd, identity, names)
            except OSError as rollback_error:
                raise rollback_error from original
        raise
    finally:
        os.close(directory_fd)


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


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

    gtf_text = (
        "chr1\ttest\texon\t100\t149\t.\t+\t.\tgene_id \"geneA\"; transcript_id \"txA\";\n"
        "chr1\ttest\texon\t200\t249\t.\t+\t.\tgene_id \"geneA\"; transcript_id \"txA\";\n"
        "chr1\ttest\texon\t130\t179\t.\t-\t.\tgene_id \"geneB\"; transcript_id \"txB\";\n"
    )
    sam_text = (
        "@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chr1\tLN:1000\n"
        "a_unique\t0\tchr1\t105\t60\t20M\t*\t0\t0\t*\t*\tNH:i:1\n"
        "a_spliced\t0\tchr1\t100\t60\t20M80N20M\t*\t0\t0\t*\t*\tNH:i:1\n"
        "b_unique\t16\tchr1\t150\t60\t20M\t*\t0\t0\t*\t*\tNH:i:1\n"
        "ambiguous\t0\tchr1\t135\t60\t10M\t*\t0\t0\t*\t*\tNH:i:1\n"
        "no_feature\t0\tchr1\t400\t60\t20M\t*\t0\t0\t*\t*\n"
        "low_mapq\t0\tchr1\t105\t10\t20M\t*\t0\t0\t*\t*\tNH:i:1\n"
        "unmapped\t4\t*\t0\t0\t*\t*\t0\t0\t*\t*\n"
        "multimap\t0\tchr1\t205\t60\t20M\t*\t0\t0\t*\t*\tNH:i:2\n"
    )
    arguments = {
        "sample_id": "sample-1",
        "strandedness": "unstranded",
        "min_mapq": 20,
    }
    first = analyze(sam_text.encode(), gtf_text.encode(), **arguments)
    repeat = analyze(sam_text.encode(), gtf_text.encode(), **arguments)
    check(first == repeat, "repeat analysis differs")
    observed = {row["gene_id"]: row["count"] for row in first["counts"]}
    check(observed == {"geneA": 2, "geneB": 1}, "gene counts differ")
    check(
        {key: first["assignment_summary"][key] for key in (
            "assigned", "ambiguous", "no_feature", "low_mapq", "unmapped", "multimapped"
        )} == {
            "assigned": 3,
            "ambiguous": 1,
            "no_feature": 1,
            "low_mapq": 1,
            "unmapped": 1,
            "multimapped": 1,
        },
        "assignment summary differs",
    )
    check(first["assignment_summary"]["mapped_primary_records_without_nh"] == 1, "missing NH not reported")
    read_group_sam = sam_text.replace(
        "@SQ\tSN:chr1\tLN:1000\n",
        "@SQ\tSN:chr1\tLN:1000\n@RG\tID:rg1\tSM:sample-1\n",
        1,
    )
    read_group = analyze(read_group_sam.encode(), gtf_text.encode(), **arguments)
    check(
        read_group["inputs"]["sam"]["read_group_sample_ids"] == ["sample-1"],
        "SAM read-group sample was not preserved",
    )
    expect(
        "sample-id-header-mismatch",
        lambda: analyze(
            read_group_sam.encode(),
            gtf_text.encode(),
            **{**arguments, "sample_id": "renamed-sample"},
        ),
    )
    expect(
        "multiple-sam-samples-out-of-scope",
        lambda: analyze(
            read_group_sam.replace(
                "@RG\tID:rg1\tSM:sample-1\n",
                "@RG\tID:rg1\tSM:sample-1\n@RG\tID:rg2\tSM:other-sample\n",
                1,
            ).encode(),
            gtf_text.encode(),
            **arguments,
        ),
    )
    expect(
        "unknown-sam-read-group",
        lambda: analyze(
            sam_text.replace("NH:i:1", "NH:i:1\tRG:Z:missing", 1).encode(),
            gtf_text.encode(),
            **arguments,
        ),
    )
    forward = analyze(sam_text.encode(), gtf_text.encode(), **{**arguments, "strandedness": "forward"})
    check(forward["assignment_summary"]["assigned"] == 4, "forward strand assignment differs")
    qc_failed = analyze(
        sam_text.replace("low_mapq\t0\t", "low_mapq\t512\t", 1).encode(),
        gtf_text.encode(),
        **arguments,
    )
    check(
        qc_failed["assignment_summary"]["qc_fail"] == 1
        and qc_failed["assignment_summary"]["low_mapq"] == 0,
        "QC-failed category precedence differs",
    )
    expect(
        "paired-sam-out-of-scope",
        lambda: analyze(sam_text.replace("a_unique\t0\t", "a_unique\t65\t", 1).encode(), gtf_text.encode(), **arguments),
    )
    expect(
        "duplicate-primary-read-name",
        lambda: analyze(sam_text.replace("a_spliced", "a_unique", 1).encode(), gtf_text.encode(), **arguments),
    )
    expect(
        "missing-or-duplicate-gtf-gene-id",
        lambda: analyze(sam_text.encode(), gtf_text.replace('gene_id "geneA"; ', "", 1).encode(), **arguments),
    )
    expect(
        "gtf-contig-not-in-sam",
        lambda: analyze(sam_text.encode(), gtf_text.replace("chr1", "chr2", 1).encode(), **arguments),
    )
    expect(
        "invalid-min-mapq",
        lambda: analyze(sam_text.encode(), gtf_text.encode(), **{**arguments, "min_mapq": 256}),
    )
    expect(
        "invalid-sam-position",
        lambda: analyze(
            sam_text.replace("chr1\t105\t60", "chr1\t" + "9" * 5000 + "\t60", 1).encode(),
            gtf_text.encode(),
            **arguments,
        ),
    )
    expect(
        "invalid-sam-cigar-operation-length",
        lambda: analyze(
            sam_text.replace("20M\t*", "9" * 5000 + "M\t*", 1).encode(),
            gtf_text.encode(),
            **arguments,
        ),
    )
    expect(
        "invalid-sam-cigar-clipping",
        lambda: analyze(
            sam_text.replace("20M\t*", "5M5S10M\t*", 1).encode(),
            gtf_text.encode(),
            **arguments,
        ),
    )
    work_sam = (
        "@HD\tVN:1.6\tSO:unsorted\n@SQ\tSN:chr1\tLN:20000\n"
        "work\t0\tchr1\t1\t60\t" + "1M1N" * 5000 + "1M\t*\t0\t0\t*\t*\tNH:i:1\n"
    )
    work_gtf = "".join(
        f'chr1\ttest\texon\t1\t1\t.\t+\t.\tgene_id "g{index}";\n'
        for index in range(1000)
    )
    expect(
        "overlap-work-too-large",
        lambda: analyze(work_sam.encode(), work_gtf.encode(), **arguments),
    )

    with tempfile.TemporaryDirectory(prefix="bio02-gene-count-selftest-") as temporary:
        root = Path(temporary)
        with working_directory(root):
            sam_path = root / "sample.sam"
            gtf_path = root / "genes.gtf"
            sam_path.write_text(sam_text, encoding="ascii")
            gtf_path.write_text(gtf_text, encoding="utf-8")
            check(read_input(sam_path, "sam", MAX_SAM_BYTES) == sam_text.encode(), "safe SAM read differs")
            symlink = root / "linked.sam"
            symlink.symlink_to(sam_path)
            expect("unreadable-sam", lambda: read_input(symlink, "sam", MAX_SAM_BYTES))
            expect("invalid-sam-path", lambda: read_input(Path("..") / "outside.sam", "sam", MAX_SAM_BYTES))
            output = root / "counts.json"
            rendered = (json.dumps(first, sort_keys=True, indent=2) + "\n").encode()
            write_new(output, rendered)
            check(output.read_bytes() == rendered, "published output differs")
            expect("output-exists", lambda: write_new(output, b"replacement\n"))

            zero_output = root / "zero.json"
            with patched_os("write", lambda _descriptor, _payload: 0):
                expect_os_error("no progress", lambda: write_new(zero_output, rendered))
            check(not zero_output.exists(), "zero-write publication left a final output")
            check(not list(root.glob(".zero.json.tmp-*")), "zero-write publication left a temporary output")

            original_write = os.write

            def short_write(descriptor: int, payload: bytes) -> int:
                return original_write(descriptor, payload[:max(1, len(payload) // 3)])

            short_output = root / "short.json"
            with patched_os("write", short_write):
                write_new(short_output, rendered)
            check(short_output.read_bytes() == rendered, "short writes truncated the output")

            unlink_output = root / "unlink.json"
            original_unlink = os.unlink
            unlink_failed = False

            def fail_postlink_unlink(path: str, *args: Any, **kwargs: Any) -> None:
                nonlocal unlink_failed
                if not unlink_failed and path.startswith(".unlink.json.tmp-"):
                    unlink_failed = True
                    raise OSError("injected post-link temporary unlink failure")
                original_unlink(path, *args, **kwargs)

            with patched_os("unlink", fail_postlink_unlink):
                expect_os_error("injected post-link", lambda: write_new(unlink_output, rendered))
            check(not unlink_output.exists(), "post-link unlink failure left a final output")
            check(not list(root.glob(".unlink.json.tmp-*")), "post-link unlink failure left a temporary output")

            fsync_output = root / "fsync.json"
            original_fsync = os.fsync
            directory_fsync_failed = False

            def fail_postlink_fsync(descriptor: int) -> None:
                nonlocal directory_fsync_failed
                if not directory_fsync_failed and stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    directory_fsync_failed = True
                    raise OSError("injected post-link directory fsync failure")
                original_fsync(descriptor)

            with patched_os("fsync", fail_postlink_fsync):
                expect_os_error("injected post-link", lambda: write_new(fsync_output, rendered))
            check(not fsync_output.exists(), "post-link fsync failure left a final output")
            check(not list(root.glob(".fsync.json.tmp-*")), "post-link fsync failure left a temporary output")

            race_output = root / "race.json"
            original_link = os.link

            def insert_competing_output(source: str, destination: str, *args: Any, **kwargs: Any) -> None:
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

            with patched_os("link", insert_competing_output):
                expect("output-exists", lambda: write_new(race_output, rendered))
            check(race_output.read_bytes() == b"competitor\n", "publication overwrote a competing output")
            check(not list(root.glob(".race.json.tmp-*")), "output race left an owned temporary output")

            identity_output = root / "identity.json"

            def replace_temporary_after_link(source: str, destination: str, *args: Any, **kwargs: Any) -> None:
                original_link(source, destination, *args, **kwargs)
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

            with patched_os("link", replace_temporary_after_link):
                expect_os_error("publication rollback failed", lambda: write_new(identity_output, rendered))
            replacements = list(root.glob(".identity.json.tmp-*"))
            check(not identity_output.exists(), "identity mismatch rollback left the owned final output")
            check(
                len(replacements) == 1 and replacements[0].read_bytes() == b"replacement\n",
                "identity mismatch rollback removed an unowned temporary output",
            )
            replacements[0].unlink()

            final_identity_output = root / "final-identity.json"
            final_identity_swapped = False

            def replace_final_during_cleanup(path: str, *args: Any, **kwargs: Any) -> None:
                nonlocal final_identity_swapped
                if not final_identity_swapped and path.startswith(".final-identity.json.tmp-"):
                    final_identity_swapped = True
                    original_unlink(final_identity_output.name, dir_fd=kwargs["dir_fd"])
                    replacement = os.open(
                        final_identity_output.name,
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

            with patched_os("unlink", replace_final_during_cleanup):
                expect_os_error("publication rollback failed", lambda: write_new(final_identity_output, rendered))
            check(
                final_identity_output.read_bytes() == b"competitor\n",
                "identity check removed a replacement final output",
            )
            check(not list(root.glob(".final-identity.json.tmp-*")), "identity check left an owned temporary output")
            final_identity_output.unlink()
            parent = root / "real-parent"
            parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(parent, target_is_directory=True)
            expect("unsafe-output-parent", lambda: write_new(linked_parent / "x.json", b"{}\n"))
    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--sam", type=Path)
    result.add_argument("--gtf", type=Path)
    result.add_argument("--sample-id")
    result.add_argument("--strandedness", choices=STRANDEDNESS)
    result.add_argument("--min-mapq", type=int)
    result.add_argument("--output", type=Path)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--version", action="version", version=VERSION)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.self_test:
        self_test()
        return 0
    required = ("sam", "gtf", "sample_id", "strandedness", "min_mapq", "output")
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
        sam_payload = read_input(arguments.sam, "sam", MAX_SAM_BYTES)
        gtf_payload = read_input(arguments.gtf, "gtf", MAX_GTF_BYTES)
        report = analyze(
            sam_payload,
            gtf_payload,
            sample_id=arguments.sample_id,
            strandedness=arguments.strandedness,
            min_mapq=arguments.min_mapq,
        )
        rendered = (json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        target = write_new(arguments.output, rendered)
        print(json.dumps({
            "analysis_performed": True,
            "assigned": report["assignment_summary"]["assigned"],
            "genes": len(report["counts"]),
            "output": target.name,
            "status": "completed",
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
