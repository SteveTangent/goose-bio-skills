#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded structural-QC report for one local GFF3 or GTF file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from urllib.parse import unquote


VERSION = "0.6.0"
MIB = 1024 * 1024
MAX_ANNOTATION_BYTES = 64 * MIB
MAX_CONTIG_SIZE_BYTES = 8 * MIB
MAX_FEATURE_RECORDS = 250_000
MAX_CONTIG_RECORDS = 100_000
MAX_RECORD_BYTES = 1 * MIB
MAX_PARENTS_PER_FEATURE = 1_024
MAX_PARENT_REFERENCES = 250_000
MAX_CYCLE_DETAIL_IDS = 20
MAX_CYCLE_ID_CHARS = 80
MAX_FINDING_EXAMPLES = 20
ALLOWED_STRANDS = {"+", "-", ".", "?"}
ALLOWED_PHASES = {"0", "1", "2", "."}
GTF_TRANSCRIPT_TYPES = {"transcript", "mrna"}
GTF_CHILD_TYPES = {
    "exon",
    "cds",
    "utr",
    "five_prime_utr",
    "three_prime_utr",
    "start_codon",
    "stop_codon",
}
BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class ContractError(Exception):
    """The requested audit cannot safely or completely run."""

    def __init__(self, code: str, message: str, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class Feature:
    line: int
    seqid: str
    feature_type: str
    start: int
    end: int
    strand: str
    identifier: str | None
    parents: tuple[str, ...]
    gene_id: str | None = None
    transcript_id: str | None = None


class Findings:
    """Keep full counts but only bounded examples for each rule."""

    def __init__(self) -> None:
        self.rule_counts: Counter[str] = Counter()
        self.severity_counts: Counter[str] = Counter()
        self.examples: list[dict[str, Any]] = []

    def add(self, severity: str, rule: str, line: int | None, detail: str) -> None:
        self.rule_counts[rule] += 1
        self.severity_counts[severity] += 1
        occurrence = self.rule_counts[rule]
        if occurrence <= MAX_FINDING_EXAMPLES:
            self.examples.append(
                {"severity": severity, "rule": rule, "line": line, "detail": detail}
            )
        elif occurrence == MAX_FINDING_EXAMPLES + 1:
            self.examples.append(
                {
                    "severity": severity,
                    "rule": rule,
                    "line": None,
                    "detail": "further examples suppressed by the fixed report cap",
                }
            )

    @property
    def error_count(self) -> int:
        return self.severity_counts["error"]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def lexical_absolute(raw: str) -> Path:
    if not raw or "\x00" in raw:
        raise ContractError("invalid-path", "path must be non-empty and contain no NUL byte")
    supplied = Path(raw)
    if ".." in supplied.parts:
        raise ContractError("parent-traversal", "parent traversal is forbidden", raw)
    return Path(os.path.abspath(os.fspath(supplied)))


def lstat_regular(path: Path, maximum: int, label: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise ContractError("path-not-found", f"{label} does not exist", str(path)) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ContractError("symlink-refused", f"{label} must not be a leaf symlink", str(path))
    if not stat.S_ISREG(metadata.st_mode):
        raise ContractError("not-regular-file", f"{label} must be a regular file", str(path))
    if metadata.st_size > maximum:
        raise ContractError(
            "input-too-large",
            f"{label} exceeds the {maximum}-byte package limit",
            str(path),
        )
    return metadata


@contextmanager
def bounded_binary_input(
    raw_path: str, maximum: int, label: str
) -> Iterator[tuple[Path, os.stat_result, BinaryIO]]:
    path = lexical_absolute(raw_path)
    before = lstat_regular(path, maximum, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContractError("input-open-failed", str(exc), str(path)) from exc
    handle: BinaryIO | None = None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ContractError("not-regular-file", f"{label} did not open as a regular file", str(path))
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ContractError("input-changed", f"{label} changed while opening", str(path))
        if opened.st_size > maximum:
            raise ContractError("input-too-large", f"{label} exceeds the package limit", str(path))
        handle = os.fdopen(descriptor, "rb")
        descriptor = -1
        yield path, opened, handle
        after = os.fstat(handle.fileno())
        current = os.lstat(path)
        if (
            stat.S_ISLNK(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise ContractError("input-changed", f"{label} changed during the audit", str(path))
    finally:
        if handle is not None:
            handle.close()
        elif descriptor >= 0:
            os.close(descriptor)


def decode_line(raw: bytes, path: Path, line: int) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(
            "non-utf8-input", f"UTF-8 decoding failed at line {line}", str(path)
        ) from exc


def parse_contig_sizes(raw_path: str) -> tuple[dict[str, int], dict[str, Any]]:
    sizes: dict[str, int] = {}
    digest = hashlib.sha256()
    byte_count = 0
    data_rows = 0
    with bounded_binary_input(raw_path, MAX_CONTIG_SIZE_BYTES, "contig-size input") as (
        path,
        metadata,
        handle,
    ):
        for line_number, raw in enumerate(handle, 1):
            byte_count += len(raw)
            if byte_count > MAX_CONTIG_SIZE_BYTES:
                raise ContractError("input-too-large", "contig-size input exceeded its byte cap", str(path))
            digest.update(raw)
            text = decode_line(raw, path, line_number).strip()
            if not text or text.startswith("#"):
                continue
            data_rows += 1
            if data_rows > MAX_CONTIG_RECORDS:
                raise ContractError(
                    "too-many-contigs",
                    f"contig-size input exceeds {MAX_CONTIG_RECORDS} data rows",
                    str(path),
                )
            fields = text.split("\t") if "\t" in text else text.split()
            if len(fields) < 2:
                raise ContractError(
                    "invalid-contig-row",
                    f"line {line_number} needs a contig name and positive length",
                    str(path),
                )
            name = fields[0]
            if not name or any(char.isspace() for char in name):
                raise ContractError("invalid-contig-name", f"invalid name at line {line_number}", str(path))
            try:
                length = int(fields[1])
            except ValueError as exc:
                raise ContractError(
                    "invalid-contig-length", f"non-integer length at line {line_number}", str(path)
                ) from exc
            if length <= 0:
                raise ContractError(
                    "invalid-contig-length", f"length must be positive at line {line_number}", str(path)
                )
            if name in sizes:
                raise ContractError(
                    "duplicate-contig", f"contig {name!r} is repeated at line {line_number}", str(path)
                )
            sizes[name] = length
    if not sizes:
        raise ContractError("empty-contig-table", "contig-size input contains no data rows", raw_path)
    return sizes, {
        "path": str(path),
        "size_bytes": metadata.st_size,
        "sha256": digest.hexdigest(),
        "contig_count": len(sizes),
    }


def split_gtf_attributes(text: str) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\" and quoted:
            current.append(char)
            escaped = True
        elif char == '"':
            quoted = not quoted
            current.append(char)
        elif char == ";" and not quoted:
            pieces.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if quoted or escaped:
        raise ValueError("unterminated quoted attribute")
    if "".join(current).strip():
        pieces.append("".join(current).strip())
    return [piece for piece in pieces if piece]


def parse_gtf_attributes(text: str) -> dict[str, str]:
    if text == ".":
        return {}
    result: dict[str, str] = {}
    for piece in split_gtf_attributes(text):
        match = re.fullmatch(r"([^\s;]+)\s+\"((?:[^\"\\]|\\.)*)\"", piece)
        if match is None:
            raise ValueError(f"malformed GTF attribute {piece!r}")
        key, encoded = match.groups()
        if key in result:
            raise ValueError(f"duplicate GTF attribute {key!r}")
        result[key] = re.sub(r"\\([\\\"])", r"\1", encoded)
    return result


def parse_gff3_attributes(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    if text == ".":
        return {}, ()
    result: dict[str, str] = {}
    parent_values: tuple[str, ...] = ()
    for piece in text.split(";"):
        if not piece:
            continue
        if "=" not in piece:
            raise ValueError(f"malformed GFF3 attribute {piece!r}")
        key, raw_value = piece.split("=", 1)
        if not key or key in result or BAD_PERCENT_ESCAPE.search(raw_value):
            raise ValueError(f"invalid or duplicate GFF3 attribute {key!r}")
        if key == "Parent":
            parent_count = raw_value.count(",") + 1
            if parent_count > MAX_PARENTS_PER_FEATURE:
                raise ContractError(
                    "too-many-parents-per-feature",
                    f"Parent exceeds {MAX_PARENTS_PER_FEATURE} identifiers",
                )
            raw_parents = raw_value.split(",")
            if any(not item for item in raw_parents):
                raise ValueError("Parent contains an empty identifier")
            parent_values = tuple(unquote(item) for item in raw_parents)
            result[key] = ",".join(parent_values)
        else:
            result[key] = unquote(raw_value)
    return result, parent_values


def coordinate_and_phase_checks(
    findings: Findings,
    line: int,
    seqid: str,
    feature_type: str,
    start_text: str,
    end_text: str,
    strand: str,
    phase: str,
    contig_sizes: dict[str, int],
) -> tuple[int, int] | None:
    try:
        start, end = int(start_text), int(end_text)
    except ValueError:
        findings.add("error", "non-integer-coordinate", line, f"start/end are {start_text!r}/{end_text!r}")
        return None
    if start < 1:
        findings.add("error", "start-below-one", line, f"start is {start}; GFF/GTF is one-based")
    if end < start:
        findings.add("error", "end-before-start", line, f"end {end} is before start {start}")
    if strand not in ALLOWED_STRANDS:
        findings.add("error", "invalid-strand", line, f"strand {strand!r} is not allowed")
    if phase not in ALLOWED_PHASES:
        findings.add("error", "invalid-phase", line, f"phase {phase!r} is not 0, 1, 2, or .")
    elif feature_type.casefold() == "cds" and phase == ".":
        findings.add("error", "cds-phase-missing", line, "CDS phase is missing")
    elif feature_type.casefold() != "cds" and phase != ".":
        findings.add("warning", "phase-on-non-cds", line, f"non-CDS feature carries phase {phase}")
    if seqid not in contig_sizes:
        findings.add("error", "contig-not-declared", line, f"contig {seqid!r} is absent from the size table")
    elif end > contig_sizes[seqid]:
        findings.add(
            "error",
            "coordinate-out-of-range",
            line,
            f"end {end} exceeds {seqid!r} length {contig_sizes[seqid]}",
        )
    if start < 1 or end < start:
        return None
    return start, end


def parse_annotation(
    raw_path: str,
    dialect: str,
    contig_sizes: dict[str, int],
) -> tuple[list[Feature], Findings, Counter[str], dict[str, Any]]:
    features: list[Feature] = []
    findings = Findings()
    feature_counts: Counter[str] = Counter()
    contigs: set[str] = set()
    digest = hashlib.sha256()
    byte_count = 0
    data_rows = 0
    parent_references = 0
    embedded_fasta_skipped = False

    with bounded_binary_input(raw_path, MAX_ANNOTATION_BYTES, "annotation input") as (
        path,
        metadata,
        handle,
    ):
        line_number = 0
        while True:
            raw = handle.readline(MAX_RECORD_BYTES + 1)
            if not raw:
                break
            line_number += 1
            if len(raw) > MAX_RECORD_BYTES:
                raise ContractError(
                    "record-too-large",
                    f"annotation record exceeds {MAX_RECORD_BYTES} bytes",
                    str(path),
                )
            byte_count += len(raw)
            if byte_count > MAX_ANNOTATION_BYTES:
                raise ContractError("input-too-large", "annotation exceeded its byte cap", str(path))
            digest.update(raw)
            text = decode_line(raw, path, line_number).rstrip("\r\n")
            if dialect == "gff3" and text == "##FASTA":
                embedded_fasta_skipped = True
                for remainder in iter(lambda: handle.read(MIB), b""):
                    byte_count += len(remainder)
                    if byte_count > MAX_ANNOTATION_BYTES:
                        raise ContractError("input-too-large", "annotation exceeded its byte cap", str(path))
                    digest.update(remainder)
                break
            if not text or text.startswith("#"):
                continue
            data_rows += 1
            if data_rows > MAX_FEATURE_RECORDS:
                raise ContractError(
                    "too-many-feature-records",
                    f"annotation exceeds {MAX_FEATURE_RECORDS} feature rows",
                    str(path),
                )
            fields = text.split("\t")
            if len(fields) != 9:
                findings.add(
                    "error", "wrong-column-count", line_number, f"found {len(fields)} columns; exactly 9 are required"
                )
                continue
            seqid, _source, feature_type, start_text, end_text, _score, strand, phase, raw_attrs = fields
            if not seqid or not feature_type:
                findings.add("error", "empty-required-field", line_number, "seqid and feature type must be non-empty")
                continue
            feature_counts[feature_type] += 1
            contigs.add(seqid)
            coordinates = coordinate_and_phase_checks(
                findings,
                line_number,
                seqid,
                feature_type,
                start_text,
                end_text,
                strand,
                phase,
                contig_sizes,
            )
            try:
                if dialect == "gff3":
                    attrs, parents = parse_gff3_attributes(raw_attrs)
                    parent_references += len(parents)
                    if parent_references > MAX_PARENT_REFERENCES:
                        raise ContractError(
                            "too-many-parent-references",
                            f"annotation exceeds {MAX_PARENT_REFERENCES} Parent references",
                            str(path),
                        )
                    identifier = attrs.get("ID")
                    if identifier == "":
                        raise ValueError("ID is empty")
                    gene_id = transcript_id = None
                else:
                    attrs = parse_gtf_attributes(raw_attrs)
                    parents = ()
                    identifier = None
                    gene_id = attrs.get("gene_id")
                    transcript_id = attrs.get("transcript_id")
            except ValueError as exc:
                findings.add("error", "malformed-attributes", line_number, str(exc))
                parents = ()
                identifier = gene_id = transcript_id = None
            if coordinates is None:
                continue
            features.append(
                Feature(
                    line=line_number,
                    seqid=seqid,
                    feature_type=feature_type,
                    start=coordinates[0],
                    end=coordinates[1],
                    strand=strand,
                    identifier=identifier,
                    parents=parents,
                    gene_id=gene_id,
                    transcript_id=transcript_id,
                )
            )

    if data_rows == 0:
        findings.add("error", "no-feature-records", None, "annotation contains no feature rows")
    details = {
        "path": str(path),
        "size_bytes": metadata.st_size,
        "sha256": digest.hexdigest(),
        "feature_record_count": data_rows,
        "parsed_feature_count": len(features),
        "annotation_contig_count": len(contigs),
        "annotation_contigs": sorted(contigs),
        "embedded_fasta_skipped": embedded_fasta_skipped,
    }
    return features, findings, feature_counts, details


def check_parent_child(findings: Findings, child: Feature, parent: Feature, parent_label: str) -> None:
    if child.seqid != parent.seqid:
        findings.add(
            "error",
            "parent-child-contig-mismatch",
            child.line,
            f"parent {parent_label!r} is on {parent.seqid!r}, child is on {child.seqid!r}",
        )
        return
    if child.strand in {"+", "-"} and parent.strand in {"+", "-"} and child.strand != parent.strand:
        findings.add(
            "error",
            "parent-child-strand-mismatch",
            child.line,
            f"parent {parent_label!r} strand {parent.strand} differs from child strand {child.strand}",
        )
    if child.start < parent.start or child.end > parent.end:
        findings.add(
            "error",
            "child-outside-parent",
            child.line,
            f"child {child.start}-{child.end} is outside parent {parent_label!r} {parent.start}-{parent.end}",
        )


def check_gff3_hierarchy(features: list[Feature], findings: Findings) -> dict[str, int]:
    identifiers: dict[str, Feature] = {}
    repeated: set[str] = set()
    invalid_repeated: set[str] = set()
    identifier_shapes: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    identifier_records: dict[str, set[tuple[str, str, int, int, str, tuple[str, ...]]]] = {}
    parent_references = 0
    for feature in features:
        identifier = feature.identifier
        if identifier is None:
            continue
        parent_key = tuple(sorted(set(feature.parents)))
        shape = (feature.seqid, feature.feature_type, feature.strand, parent_key)
        record = (
            feature.seqid,
            feature.feature_type,
            feature.start,
            feature.end,
            feature.strand,
            parent_key,
        )
        previous = identifiers.get(identifier)
        if previous is None:
            identifiers[identifier] = feature
            identifier_shapes[identifier] = shape
            identifier_records[identifier] = {record}
            continue
        repeated.add(identifier)
        seen_records = identifier_records[identifier]
        if record in seen_records:
            rule, detail = "duplicate-id", f"ID {identifier!r} repeats an identical declaration"
            severity = "error"
        elif shape == identifier_shapes[identifier] and identifier not in invalid_repeated:
            rule, detail = (
                "repeated-id-discontinuous",
                f"ID {identifier!r} repeats with compatible metadata; review discontinuous-feature intent",
            )
            severity = "warning"
        else:
            rule, detail = "conflicting-duplicate-id", f"ID {identifier!r} has conflicting declarations"
            severity = "error"
        findings.add(severity, rule, feature.line, detail)
        seen_records.add(record)
        if severity == "error":
            invalid_repeated.add(identifier)

    ambiguous_reported: set[str] = set()
    for child in features:
        for parent_id in child.parents:
            parent_references += 1
            parent = identifiers.get(parent_id)
            if parent is None:
                findings.add("error", "orphan-parent", child.line, f"Parent {parent_id!r} is not declared")
            elif parent_id in repeated:
                if parent_id not in ambiguous_reported:
                    findings.add(
                        "warning",
                        "ambiguous-parent-id",
                        child.line,
                        f"containment was not inferred through repeated Parent {parent_id!r}",
                    )
                    ambiguous_reported.add(parent_id)
            else:
                check_parent_child(findings, child, parent, parent_id)

    graph = {
        identifier: tuple(
            dict.fromkeys(
                parent_id
                for parent_id in feature.parents
                if parent_id in identifiers and parent_id not in invalid_repeated
            )
        )
        for identifier, feature in identifiers.items()
        if identifier not in invalid_repeated
    }
    state: dict[str, int] = {}
    for start in sorted(graph):
        if state.get(start, 0) != 0:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        positions: dict[str, int] = {}
        while stack:
            node, next_parent = stack[-1]
            if state.get(node, 0) == 0:
                state[node] = 1
                positions[node] = len(path)
                path.append(node)
            parents = graph.get(node, ())
            if next_parent < len(parents):
                parent_id = parents[next_parent]
                stack[-1] = (node, next_parent + 1)
                parent_state = state.get(parent_id, 0)
                if parent_state == 0:
                    stack.append((parent_id, 0))
                elif parent_state == 1:
                    position = positions[parent_id]
                    cycle_length = len(path) - position
                    preview_ids = path[position : position + MAX_CYCLE_DETAIL_IDS]
                    rendered = [
                        value
                        if len(value) <= MAX_CYCLE_ID_CHARS
                        else f"{value[:MAX_CYCLE_ID_CHARS]}..."
                        for value in preview_ids
                    ]
                    if cycle_length > MAX_CYCLE_DETAIL_IDS:
                        rendered.append(f"... {cycle_length - MAX_CYCLE_DETAIL_IDS} omitted ...")
                    rendered.append(
                        parent_id
                        if len(parent_id) <= MAX_CYCLE_ID_CHARS
                        else f"{parent_id[:MAX_CYCLE_ID_CHARS]}..."
                    )
                    findings.add(
                        "error",
                        "parent-cycle",
                        identifiers[node].line,
                        f"Parent relationship forms a {cycle_length}-ID cycle: {' -> '.join(rendered)}",
                    )
                continue
            state[node] = 2
            stack.pop()
            positions.pop(node, None)
            if path and path[-1] == node:
                path.pop()
    return {
        "unique_identifier_count": len(identifiers),
        "repeated_identifier_count": len(repeated),
        "parent_reference_count": parent_references,
    }


def check_gtf_hierarchy(features: list[Feature], findings: Findings) -> dict[str, int]:
    genes: dict[str, Feature] = {}
    transcripts: dict[str, Feature] = {}
    transcript_rows: list[Feature] = []
    child_rows: list[Feature] = []

    for feature in features:
        kind = feature.feature_type.casefold()
        if kind == "gene":
            if not feature.gene_id:
                findings.add("error", "missing-gene-id", feature.line, "gene feature lacks gene_id")
            elif feature.gene_id in genes:
                findings.add(
                    "error",
                    "duplicate-gene-id",
                    feature.line,
                    f"gene_id {feature.gene_id!r} is redeclared",
                )
            else:
                genes[feature.gene_id] = feature
        elif kind in GTF_TRANSCRIPT_TYPES:
            if not feature.gene_id:
                findings.add("error", "missing-gene-id", feature.line, "transcript feature lacks gene_id")
            if not feature.transcript_id:
                findings.add("error", "missing-transcript-id", feature.line, "transcript feature lacks transcript_id")
            elif feature.transcript_id in transcripts:
                findings.add(
                    "error", "duplicate-transcript-id", feature.line, f"transcript_id {feature.transcript_id!r} is redeclared"
                )
            else:
                transcripts[feature.transcript_id] = feature
            transcript_rows.append(feature)
        elif kind in GTF_CHILD_TYPES:
            if not feature.gene_id:
                findings.add("error", "missing-gene-id", feature.line, f"{feature.feature_type} lacks gene_id")
            if not feature.transcript_id:
                findings.add(
                    "error", "missing-transcript-id", feature.line, f"{feature.feature_type} lacks transcript_id"
                )
            child_rows.append(feature)

    for transcript in transcript_rows:
        if not transcript.gene_id:
            continue
        gene = genes.get(transcript.gene_id)
        if gene is None:
            findings.add(
                "error", "orphan-gene-reference", transcript.line, f"gene_id {transcript.gene_id!r} is not declared"
            )
        else:
            check_parent_child(findings, transcript, gene, transcript.gene_id)

    for child in child_rows:
        if child.transcript_id:
            transcript = transcripts.get(child.transcript_id)
            if transcript is None:
                findings.add(
                    "error",
                    "orphan-transcript-reference",
                    child.line,
                    f"transcript_id {child.transcript_id!r} is not declared",
                )
            else:
                check_parent_child(findings, child, transcript, child.transcript_id)
                if (
                    child.gene_id
                    and transcript.gene_id
                    and child.gene_id != transcript.gene_id
                ):
                    findings.add(
                        "error",
                        "child-transcript-gene-mismatch",
                        child.line,
                        (
                            f"child gene_id {child.gene_id!r} differs from transcript "
                            f"{child.transcript_id!r} gene_id {transcript.gene_id!r}"
                        ),
                    )
        if child.gene_id:
            gene = genes.get(child.gene_id)
            if gene is None:
                findings.add(
                    "error", "orphan-gene-reference", child.line, f"gene_id {child.gene_id!r} is not declared"
                )
            else:
                check_parent_child(findings, child, gene, child.gene_id)

    return {
        "declared_gene_count": len(genes),
        "declared_transcript_count": len(transcripts),
        "hierarchical_child_count": len(child_rows),
    }


def build_report(annotation: str, dialect: str, contig_sizes_path: str) -> dict[str, Any]:
    if dialect not in {"gff3", "gtf"}:
        raise ContractError("invalid-format", "format must be gff3 or gtf")
    sizes, sizes_input = parse_contig_sizes(contig_sizes_path)
    features, findings, feature_counts, annotation_input = parse_annotation(annotation, dialect, sizes)
    hierarchy = (
        check_gff3_hierarchy(features, findings)
        if dialect == "gff3"
        else check_gtf_hierarchy(features, findings)
    )
    annotation_contigs = set(annotation_input["annotation_contigs"])
    unused_contigs = sorted(set(sizes) - annotation_contigs)
    return {
        "schema_version": "0.1.0",
        "tool": "check_gene_models.py",
        "tool_version": VERSION,
        "python_version": platform.python_version(),
        "created_at": now_utc(),
        "status": "completed",
        "structural_qc_performed": True,
        "scientific_completeness_assessed": False,
        "annotation_format": dialect,
        "inputs": {"annotation": annotation_input, "contig_sizes": sizes_input},
        "limits": {
            "max_annotation_bytes": MAX_ANNOTATION_BYTES,
            "max_contig_size_bytes": MAX_CONTIG_SIZE_BYTES,
            "max_feature_records": MAX_FEATURE_RECORDS,
            "max_contig_records": MAX_CONTIG_RECORDS,
            "max_record_bytes": MAX_RECORD_BYTES,
            "max_parents_per_feature": MAX_PARENTS_PER_FEATURE,
            "max_parent_references": MAX_PARENT_REFERENCES,
            "max_cycle_detail_ids": MAX_CYCLE_DETAIL_IDS,
            "max_examples_per_rule": MAX_FINDING_EXAMPLES,
            "compression": False,
            "recursion": False,
            "network": False,
            "subprocess": False,
        },
        "summary": {
            "structural_status": "issues-detected" if findings.error_count else "no-errors-detected",
            "error_count": findings.error_count,
            "warning_count": findings.severity_counts["warning"],
            "feature_counts": dict(sorted(feature_counts.items())),
            "annotation_contig_count": len(annotation_contigs),
            "declared_contig_count": len(sizes),
            "declared_but_unused_contig_count": len(unused_contigs),
            "declared_but_unused_contig_examples": unused_contigs[:MAX_FINDING_EXAMPLES],
            **hierarchy,
        },
        "finding_counts": dict(sorted(findings.rule_counts.items())),
        "findings": findings.examples,
        "limitations": [
            "Structural checks do not establish biological gene-model quality or completeness.",
            "CDS phase tokens are checked, but cross-segment frame continuity and translation are not reconstructed.",
            "Repeated compatible GFF3 IDs are reported for review rather than merged as discontinuous features.",
            "Contig identifiers are compared exactly; no assembly or chr-prefix equivalence is inferred.",
        ],
    }


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_new_json(raw_path: str, report: dict[str, Any]) -> Path:
    target = lexical_absolute(raw_path)
    try:
        parent_state = os.lstat(target.parent)
    except FileNotFoundError as exc:
        raise ContractError("output-parent-missing", "output parent must already exist", str(target.parent)) from exc
    if stat.S_ISLNK(parent_state.st_mode) or not stat.S_ISDIR(parent_state.st_mode):
        raise ContractError("unsafe-output-parent", "output parent must be a real directory", str(target.parent))
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    else:
        raise ContractError("output-exists", "output exists; overwrite is forbidden", str(target))

    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
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
            raise ContractError("output-exists", "output appeared; overwrite is forbidden", str(target)) from exc
        published = True
        fsync_directory(target.parent)
    except BaseException:
        if published:
            try:
                target_state = os.lstat(target)
                temporary_state = os.lstat(temporary)
                if (target_state.st_dev, target_state.st_ino) == (
                    temporary_state.st_dev,
                    temporary_state.st_ino,
                ):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return target


def expect_contract_error(code: str, action: Any) -> None:
    try:
        action()
    except ContractError as exc:
        if exc.code != code:
            raise AssertionError(f"expected {code}, got {exc.code}") from exc
    else:
        raise AssertionError(f"expected {code}")


def require_test(condition: bool, message: str) -> None:
    """Keep self-test checks active even when Python runs with optimization."""

    if not condition:
        raise RuntimeError(message)


def self_test() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="bio02-gene-model-qc-") as temporary:
        root = Path(temporary)
        sizes = root / "tiny.fa.fai"
        sizes.write_text("chr1\t1000\t0\t50\t51\nchr2\t500\t0\t50\t51\n", encoding="utf-8")

        good_gff = root / "good.gff3"
        good_gff.write_text(
            "##gff-version 3\n"
            "chr1\tsrc\tgene\t100\t500\t.\t+\t.\tID=g1\n"
            "chr1\tsrc\tmRNA\t120\t480\t.\t+\t.\tID=t1;Parent=g1\n"
            "chr1\tsrc\texon\t120\t200\t.\t+\t.\tID=e1;Parent=t1\n"
            "chr1\tsrc\tCDS\t150\t200\t.\t+\t0\tID=c1;Parent=t1\n",
            encoding="utf-8",
        )
        clean = build_report(str(good_gff), "gff3", str(sizes))
        require_test(clean["summary"]["error_count"] == 0, "clean GFF3 has errors")
        require_test(clean["summary"]["feature_counts"]["CDS"] == 1, "clean GFF3 CDS count differs")
        checks += 1

        bad_gff = root / "bad.gff3"
        bad_gff.write_text(
            "chr1\tsrc\tgene\t100\t200\t.\t+\t.\tID=g1\n"
            "chr1\tsrc\tgene\t100\t200\t.\t+\t.\tID=g1\n"
            "chr1\tsrc\tgene\t300\t350\t.\t+\t.\tID=g2\n"
            "chr1\tsrc\tCDS\t340\t370\t.\t+\t.\tID=c1;Parent=g2\n"
            "chr1\tsrc\tmRNA\t400\t450\t.\t+\t.\tID=cycle;Parent=cycle\n"
            "chr1\tsrc\tmRNA\t500\t550\t.\t+\t.\tID=cycle-a;Parent=cycle-b\n"
            "chr1\tsrc\tmRNA\t500\t550\t.\t+\t.\tID=cycle-b;Parent=cycle-a\n"
            "chrX\tsrc\texon\t1\t10\t.\t+\t.\tID=e1;Parent=missing\n",
            encoding="utf-8",
        )
        broken = build_report(str(bad_gff), "gff3", str(sizes))
        for rule in (
            "duplicate-id",
            "cds-phase-missing",
            "child-outside-parent",
            "parent-cycle",
            "orphan-parent",
            "contig-not-declared",
        ):
            require_test(broken["finding_counts"][rule] >= 1, f"missing GFF3 finding: {rule}")
        require_test(broken["finding_counts"]["parent-cycle"] == 2, "GFF3 parent-cycle count differs")
        checks += 1

        discontinuous_gff = root / "discontinuous.gff3"
        discontinuous_gff.write_text(
            "##gff-version 3\n"
            "chr1\tsrc\tgene\t1\t300\t.\t+\t.\tID=dg1\n"
            "chr1\tsrc\tgene\t1\t300\t.\t+\t.\tID=dg2\n"
            "chr1\tsrc\tCDS\t10\t20\t.\t+\t0\tID=dc;Parent=dg1,dg2\n"
            "chr1\tsrc\tCDS\t30\t40\t.\t+\t0\tID=dc;Parent=dg2,dg1\n",
            encoding="utf-8",
        )
        discontinuous = build_report(str(discontinuous_gff), "gff3", str(sizes))
        require_test(discontinuous["summary"]["error_count"] == 0, "legal discontinuous GFF3 ID was rejected")
        require_test(
            discontinuous["finding_counts"]["repeated-id-discontinuous"] == 1,
            "legal discontinuous GFF3 ID was not reported",
        )
        require_test(discontinuous["finding_counts"].get("parent-cycle", 0) == 0, "acyclic GFF3 was called cyclic")
        checks += 1

        duplicate_segment_gff = root / "duplicate-segment.gff3"
        duplicate_segment_gff.write_text(
            "##gff-version 3\n"
            "chr1\tsrc\tgene\t1\t300\t.\t+\t.\tID=sg\n"
            "chr1\tsrc\tCDS\t10\t20\t.\t+\t0\tID=sc;Parent=sg\n"
            "chr1\tsrc\tCDS\t30\t40\t.\t+\t0\tID=sc;Parent=sg\n"
            "chr1\tsrc\tCDS\t30\t40\t.\t+\t0\tID=sc;Parent=sg\n",
            encoding="utf-8",
        )
        duplicate_segment = build_report(str(duplicate_segment_gff), "gff3", str(sizes))
        require_test(duplicate_segment["finding_counts"]["duplicate-id"] == 1, "later duplicate segment was missed")
        checks += 1

        repeated_cycle_gff = root / "repeated-cycle.gff3"
        repeated_cycle_gff.write_text(
            "##gff-version 3\n"
            "chr1\tsrc\tmRNA\t100\t300\t.\t+\t.\tID=ra;Parent=rb\n"
            "chr1\tsrc\tmRNA\t120\t280\t.\t+\t.\tID=ra;Parent=rb\n"
            "chr1\tsrc\tmRNA\t100\t300\t.\t+\t.\tID=rb;Parent=ra\n",
            encoding="utf-8",
        )
        repeated_cycle = build_report(str(repeated_cycle_gff), "gff3", str(sizes))
        require_test(
            repeated_cycle["finding_counts"]["parent-cycle"] == 1,
            "cycle through a compatible discontinuous ID was missed",
        )
        checks += 1

        good_gtf = root / "good.gtf"
        good_gtf.write_text(
            'chr1\tsrc\tgene\t10\t400\t.\t-\t.\tgene_id "G";\n'
            'chr1\tsrc\ttranscript\t20\t390\t.\t-\t.\tgene_id "G"; transcript_id "T";\n'
            'chr1\tsrc\texon\t20\t100\t.\t-\t.\tgene_id "G"; transcript_id "T";\n'
            'chr1\tsrc\tCDS\t40\t100\t.\t-\t2\tgene_id "G"; transcript_id "T";\n',
            encoding="utf-8",
        )
        gtf_report = build_report(str(good_gtf), "gtf", str(sizes))
        require_test(gtf_report["summary"]["error_count"] == 0, "clean GTF has errors")
        require_test(gtf_report["summary"]["declared_transcript_count"] == 1, "clean GTF transcript count differs")
        checks += 1

        bad_gtf = root / "bad.gtf"
        bad_gtf.write_text(
            'chr1\tsrc\tgene\t1\t50\t.\t+\t.\tgene_id "G";\n'
            'chr1\tsrc\tgene\t1\t50\t.\t+\t.\tgene_id "G";\n'
            'chr1\tsrc\texon\t60\t70\t.\t+\t.\tgene_id "missing"; transcript_id "missing";\n',
            encoding="utf-8",
        )
        bad_gtf_report = build_report(str(bad_gtf), "gtf", str(sizes))
        require_test(bad_gtf_report["finding_counts"]["duplicate-gene-id"] == 1, "duplicate GTF gene was missed")
        require_test(bad_gtf_report["finding_counts"]["orphan-transcript-reference"] == 1, "orphan GTF transcript was missed")
        checks += 1

        mismatched_gtf = root / "mismatched.gtf"
        mismatched_gtf.write_text(
            'chr1\tsrc\tgene\t1\t200\t.\t+\t.\tgene_id "G1";\n'
            'chr1\tsrc\tgene\t1\t200\t.\t+\t.\tgene_id "G2";\n'
            'chr1\tsrc\ttranscript\t10\t190\t.\t+\t.\tgene_id "G1"; transcript_id "T1";\n'
            'chr1\tsrc\texon\t20\t100\t.\t+\t.\tgene_id "G2"; transcript_id "T1";\n',
            encoding="utf-8",
        )
        mismatch_report = build_report(str(mismatched_gtf), "gtf", str(sizes))
        require_test(
            mismatch_report["finding_counts"]["child-transcript-gene-mismatch"] == 1,
            "cross-gene GTF transcript child was missed",
        )
        checks += 1

        output = root / "report.json"
        write_new_json(str(output), clean)
        before = output.read_bytes()
        expect_contract_error("output-exists", lambda: write_new_json(str(output), clean))
        require_test(output.read_bytes() == before, "existing output changed")
        checks += 1

        symlink = root / "linked.gff3"
        os.symlink(good_gff, symlink)
        expect_contract_error(
            "symlink-refused", lambda: build_report(str(symlink), "gff3", str(sizes))
        )
        checks += 1

        original_limit = globals()["MAX_FEATURE_RECORDS"]
        globals()["MAX_FEATURE_RECORDS"] = 1
        try:
            expect_contract_error(
                "too-many-feature-records",
                lambda: build_report(str(good_gff), "gff3", str(sizes)),
            )
        finally:
            globals()["MAX_FEATURE_RECORDS"] = original_limit
        checks += 1

        original_record_limit = globals()["MAX_RECORD_BYTES"]
        globals()["MAX_RECORD_BYTES"] = 20
        try:
            expect_contract_error(
                "record-too-large",
                lambda: build_report(str(good_gff), "gff3", str(sizes)),
            )
        finally:
            globals()["MAX_RECORD_BYTES"] = original_record_limit
        checks += 1

        original_parent_limit = globals()["MAX_PARENTS_PER_FEATURE"]
        globals()["MAX_PARENTS_PER_FEATURE"] = 1
        try:
            expect_contract_error(
                "too-many-parents-per-feature",
                lambda: build_report(str(discontinuous_gff), "gff3", str(sizes)),
            )
        finally:
            globals()["MAX_PARENTS_PER_FEATURE"] = original_parent_limit
        checks += 1

        original_reference_limit = globals()["MAX_PARENT_REFERENCES"]
        globals()["MAX_PARENT_REFERENCES"] = 1
        try:
            expect_contract_error(
                "too-many-parent-references",
                lambda: build_report(str(good_gff), "gff3", str(sizes)),
            )
        finally:
            globals()["MAX_PARENT_REFERENCES"] = original_reference_limit
        checks += 1

        require_test(clean["scientific_completeness_assessed"] is False, "scientific completeness claim changed")
        require_test(
            clean["limits"]["network"] is False and clean["limits"]["subprocess"] is False,
            "offline execution boundary changed",
        )
        checks += 1

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation")
    parser.add_argument("--format", choices=("gff3", "gtf"))
    parser.add_argument("--contig-sizes")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        if any((args.annotation, args.format, args.contig_sizes, args.output)):
            parser.error("--self-test cannot be combined with audit arguments")
        self_test()
        return 0
    if not all((args.annotation, args.format, args.contig_sizes, args.output)):
        parser.error("--annotation, --format, --contig-sizes, and --output are required")
    try:
        report = build_report(args.annotation, args.format, args.contig_sizes)
        write_new_json(args.output, report)
    except ContractError as exc:
        print(
            json.dumps(
                {"status": "invalid-input", "analysis_performed": False, "error": exc.as_dict()},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    return 1 if report["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
