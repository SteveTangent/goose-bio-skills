#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a bounded heavy-atom contact report for two legacy-PDB chains."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator


VERSION = "0.7.0"
MIB = 1024 * 1024
MAX_INPUT_BYTES = 32 * MIB
MAX_LINES = 500_000
MAX_RECORD_BYTES = 4 * 1024
MAX_COORDINATE_RECORDS = 250_000
MAX_SELECTED_RECORDS_PER_CHAIN = 25_000
MAX_PAIR_COMPARISONS = 10_000_000
MAX_CUTOFF_ANGSTROM = 20.0
HYDROGEN_ELEMENTS = {"H", "D", "T"}
VALID_ELEMENTS = {
    "AC", "AG", "AL", "AM", "AR", "AS", "AT", "AU", "B", "BA", "BE",
    "BH", "BI", "BK", "BR", "C", "CA", "CD", "CE", "CF", "CL", "CM",
    "CN", "CO", "CR", "CS", "CU", "D", "DB", "DS", "DY", "ER", "ES",
    "EU", "F", "FE", "FL", "FM", "FR", "GA", "GD", "GE", "H", "HE",
    "HF", "HG", "HO", "HS", "I", "IN", "IR", "K", "KR", "LA", "LI",
    "LR", "LU", "LV", "MC", "MD", "MG", "MN", "MO", "MT", "N", "NA",
    "NB", "ND", "NE", "NH", "NI", "NO", "NP", "O", "OG", "OS", "P",
    "PA", "PB", "PD", "PM", "PO", "PR", "PT", "PU", "RA", "RB", "RE",
    "RF", "RG", "RH", "RN", "RU", "S", "SB", "SC", "SE", "SG", "SI",
    "SM", "SN", "SR", "TA", "TB", "TC", "TE", "TH", "TI", "TL", "TM",
    "TS", "U", "V", "W", "XE", "Y", "YB", "ZN", "ZR",
}
ELEMENT_TOKEN = re.compile(r"[A-Za-z]{1,2}")


class ContractError(Exception):
    """The requested analysis cannot safely or completely run."""

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
class ResidueKey:
    chain: str
    sequence_number: int
    insertion_code: str
    name: str


@dataclass(frozen=True)
class Atom:
    residue: ResidueKey
    name: str
    element: str
    x: float
    y: float
    z: float
    record_type: str


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
        after_open = os.fstat(handle.fileno())
        after_path = os.lstat(path)
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


def validate_parameters(chain_a: str, chain_b: str, cutoff: float) -> None:
    for label, chain in (("chain-a", chain_a), ("chain-b", chain_b)):
        if len(chain) != 1 or chain.isspace() or not chain.isascii() or not chain.isprintable():
            raise ContractError(
                "invalid-chain-id",
                f"{label} must be one nonblank printable ASCII character",
            )
    if chain_a == chain_b:
        raise ContractError("same-chain", "chain-a and chain-b must be distinct")
    if not math.isfinite(cutoff) or not 0.0 < cutoff <= MAX_CUTOFF_ANGSTROM:
        raise ContractError(
            "invalid-cutoff",
            f"cutoff must be finite and in (0, {MAX_CUTOFF_ANGSTROM}] angstrom",
        )


def parse_float(field: str, label: str, line_number: int) -> float:
    try:
        value = float(field)
    except ValueError as exc:
        raise ContractError("invalid-coordinate", f"{label} is invalid at line {line_number}") from exc
    if not math.isfinite(value):
        raise ContractError("non-finite-coordinate", f"{label} is non-finite at line {line_number}")
    return value


def parse_selected_atom(text: str, record_type: str, line_number: int) -> Atom | None:
    if len(text) < 78:
        raise ContractError(
            "short-coordinate-record",
            f"selected coordinate record is shorter than 78 columns at line {line_number}",
        )
    altloc = text[16]
    if altloc != " ":
        raise ContractError(
            "alternate-location-unsupported",
            f"alternate location {altloc!r} occurs at line {line_number}",
            status="needs-tool",
        )
    atom_name = text[12:16].strip()
    residue_name = text[17:20].strip()
    if not atom_name or not residue_name:
        raise ContractError("missing-atom-or-residue-name", f"missing name at line {line_number}")
    try:
        sequence_number = int(text[22:26])
    except ValueError as exc:
        raise ContractError(
            "invalid-residue-number",
            f"residue sequence number is invalid at line {line_number}",
        ) from exc
    raw_element = text[76:78].strip()
    if not ELEMENT_TOKEN.fullmatch(raw_element):
        raise ContractError(
            "missing-or-invalid-element",
            f"element columns are missing or invalid at line {line_number}",
        )
    element = raw_element.upper()
    if element not in VALID_ELEMENTS:
        raise ContractError("unknown-element", f"unknown element {raw_element!r} at line {line_number}")
    if element in HYDROGEN_ELEMENTS:
        return None
    residue = ResidueKey(
        chain=text[21],
        sequence_number=sequence_number,
        insertion_code="" if text[26] == " " else text[26],
        name=residue_name,
    )
    return Atom(
        residue=residue,
        name=atom_name,
        element=element,
        x=parse_float(text[30:38], "x", line_number),
        y=parse_float(text[38:46], "y", line_number),
        z=parse_float(text[46:54], "z", line_number),
        record_type=record_type,
    )


def parse_pdb(raw_path: str, chain_a: str, chain_b: str) -> tuple[list[Atom], list[Atom], dict[str, Any]]:
    digest = hashlib.sha256()
    atoms: dict[str, list[Atom]] = {chain_a: [], chain_b: []}
    selected_records = {chain_a: 0, chain_b: 0}
    coordinate_records = 0
    line_count = 0
    model_count = 0
    in_model = False
    ended_model = False
    coordinate_before_model = False
    residue_names: dict[tuple[str, int, str], str] = {}
    atom_names: set[tuple[ResidueKey, str]] = set()

    with bounded_binary_input(raw_path) as (_, metadata, handle):
        for line_number, raw in enumerate(handle, 1):
            line_count = line_number
            if line_count > MAX_LINES:
                raise ContractError(
                    "too-many-lines",
                    f"input exceeds {MAX_LINES} lines",
                    status="needs-tool",
                )
            if len(raw) > MAX_RECORD_BYTES:
                raise ContractError(
                    "record-too-long",
                    f"line {line_number} exceeds {MAX_RECORD_BYTES} bytes",
                    status="needs-tool",
                )
            digest.update(raw)
            try:
                text = raw.rstrip(b"\r\n").decode("ascii")
            except UnicodeDecodeError as exc:
                raise ContractError("non-ascii-input", f"non-ASCII byte at line {line_number}") from exc
            record_type = text[0:6].strip() if text else ""

            if record_type == "MODEL":
                if model_count or coordinate_before_model:
                    raise ContractError(
                        "multiple-models-unsupported",
                        "more than one coordinate model is unsupported",
                        status="needs-tool",
                    )
                model_count = 1
                in_model = True
                continue
            if record_type == "ENDMDL":
                if not in_model:
                    raise ContractError("invalid-model-layout", f"unexpected ENDMDL at line {line_number}")
                in_model = False
                ended_model = True
                continue
            if record_type not in {"ATOM", "HETATM"}:
                continue
            coordinate_records += 1
            if coordinate_records > MAX_COORDINATE_RECORDS:
                raise ContractError(
                    "too-many-coordinate-records",
                    f"input exceeds {MAX_COORDINATE_RECORDS} coordinate records",
                    status="needs-tool",
                )
            if model_count and (not in_model or ended_model):
                raise ContractError("invalid-model-layout", f"coordinate outside MODEL at line {line_number}")
            if not model_count:
                coordinate_before_model = True
            if len(text) < 22:
                raise ContractError("short-coordinate-record", f"coordinate record is too short at line {line_number}")
            chain = text[21]
            if chain not in atoms:
                continue
            selected_records[chain] += 1
            if selected_records[chain] > MAX_SELECTED_RECORDS_PER_CHAIN:
                raise ContractError(
                    "too-many-selected-records",
                    f"chain {chain!r} exceeds {MAX_SELECTED_RECORDS_PER_CHAIN} selected records",
                    status="needs-tool",
                )
            atom = parse_selected_atom(text, record_type, line_number)
            if atom is None:
                continue
            position = (
                atom.residue.chain,
                atom.residue.sequence_number,
                atom.residue.insertion_code,
            )
            prior_name = residue_names.setdefault(position, atom.residue.name)
            if prior_name != atom.residue.name:
                raise ContractError(
                    "ambiguous-residue-position",
                    f"residue position {position!r} has conflicting names",
                )
            identity = (atom.residue, atom.name)
            if identity in atom_names:
                raise ContractError(
                    "duplicate-atom",
                    f"atom {atom.name!r} is duplicated in residue {atom.residue!r}",
                )
            atom_names.add(identity)
            atoms[chain].append(atom)

        if in_model:
            raise ContractError("invalid-model-layout", "MODEL block is missing ENDMDL")

    for chain in (chain_a, chain_b):
        if selected_records[chain] == 0:
            raise ContractError("chain-not-found", f"chain {chain!r} has no ATOM/HETATM records")
        if not atoms[chain]:
            raise ContractError("no-heavy-atoms", f"chain {chain!r} has no retained heavy atoms")
        atoms[chain].sort(
            key=lambda atom: (
                atom.residue,
                atom.name,
                atom.element,
                atom.x,
                atom.y,
                atom.z,
                atom.record_type,
            )
        )

    return atoms[chain_a], atoms[chain_b], {
        "sha256": digest.hexdigest(),
        "size_bytes": metadata.st_size,
        "line_count": line_count,
        "coordinate_record_count": coordinate_records,
        "model_record_mode": "single-model-block" if model_count else "no-model-records",
    }


def residue_dict(residue: ResidueKey, record_types: set[str]) -> dict[str, Any]:
    return {
        "chain": residue.chain,
        "name": residue.name,
        "sequence_number": residue.sequence_number,
        "insertion_code": residue.insertion_code,
        "record_types": sorted(record_types),
    }


def find_contacts(
    atoms_a: list[Atom],
    atoms_b: list[Atom],
    cutoff: float,
    *,
    max_pair_comparisons: int = MAX_PAIR_COMPARISONS,
) -> tuple[list[dict[str, Any]], int]:
    comparisons = len(atoms_a) * len(atoms_b)
    if comparisons > max_pair_comparisons:
        raise ContractError(
            "pair-cap-exceeded",
            f"{comparisons} atom comparisons exceed the {max_pair_comparisons} limit",
            status="needs-tool",
        )
    cutoff_squared = cutoff * cutoff
    minima: dict[tuple[ResidueKey, ResidueKey], tuple[float, tuple[str, str, str, str]]] = {}
    types: dict[ResidueKey, set[str]] = {}
    for atom in (*atoms_a, *atoms_b):
        types.setdefault(atom.residue, set()).add(atom.record_type)

    # ponytail: bounded O(n*m) is clearer; add a spatial index only when real inputs exceed the cap.
    for atom_a in atoms_a:
        for atom_b in atoms_b:
            dx = atom_a.x - atom_b.x
            dy = atom_a.y - atom_b.y
            dz = atom_a.z - atom_b.z
            distance_squared = dx * dx + dy * dy + dz * dz
            if distance_squared > cutoff_squared:
                continue
            key = (atom_a.residue, atom_b.residue)
            labels = (atom_a.name, atom_a.element, atom_b.name, atom_b.element)
            prior = minima.get(key)
            if prior is None or (distance_squared, labels) < prior:
                minima[key] = (distance_squared, labels)

    contacts: list[dict[str, Any]] = []
    for (residue_a, residue_b), (distance_squared, labels) in sorted(minima.items()):
        atom_a_name, element_a, atom_b_name, element_b = labels
        contacts.append(
            {
                "residue_a": residue_dict(residue_a, types[residue_a]),
                "residue_b": residue_dict(residue_b, types[residue_b]),
                "minimum_distance_angstrom": round(math.sqrt(distance_squared), 6),
                "minimum_atom_pair": {
                    "atom_a": atom_a_name,
                    "element_a": element_a,
                    "atom_b": atom_b_name,
                    "element_b": element_b,
                },
            }
        )
    return contacts, comparisons


def build_report(input_path: str, chain_a: str, chain_b: str, cutoff: float) -> dict[str, Any]:
    validate_parameters(chain_a, chain_b, cutoff)
    atoms_a, atoms_b, input_details = parse_pdb(input_path, chain_a, chain_b)
    contacts, comparisons = find_contacts(atoms_a, atoms_b, cutoff)
    residues_a = {atom.residue for atom in atoms_a}
    residues_b = {atom.residue for atom in atoms_b}
    return {
        "schema_version": "0.1.0",
        "tool": "analyze_contacts.py",
        "tool_version": VERSION,
        "status": "completed",
        "analysis": "heavy-atom-residue-contacts",
        "input": input_details,
        "parameters": {
            "chain_a": chain_a,
            "chain_b": chain_b,
            "cutoff_angstrom": cutoff,
            "coordinate_record_types": ["ATOM", "HETATM"],
            "excluded_elements": sorted(HYDROGEN_ELEMENTS),
            "alternate_location_policy": "reject-nonblank",
        },
        "limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "max_lines": MAX_LINES,
            "max_record_bytes": MAX_RECORD_BYTES,
            "max_coordinate_records": MAX_COORDINATE_RECORDS,
            "max_selected_records_per_chain": MAX_SELECTED_RECORDS_PER_CHAIN,
            "max_pair_comparisons": MAX_PAIR_COMPARISONS,
            "max_cutoff_angstrom": MAX_CUTOFF_ANGSTROM,
            "network": False,
            "subprocess": False,
            "compression": False,
        },
        "summary": {
            "chain_a_heavy_atom_count": len(atoms_a),
            "chain_b_heavy_atom_count": len(atoms_b),
            "chain_a_residue_count": len(residues_a),
            "chain_b_residue_count": len(residues_b),
            "atom_pair_comparisons": comparisons,
            "contact_count": len(contacts),
        },
        "contacts": contacts,
        "limitations": [
            "Geometric contacts do not prove a biological assembly, binding, affinity, or function.",
            "ATOM and HETATM coordinates are included without polymer, ligand, solvent, or occupancy interpretation.",
            "The helper refuses alternate conformers and multiple coordinate models rather than selecting among them.",
            "Residue identifiers are reported exactly; no renumbering or equivalence is inferred.",
            "Only legacy fixed-column PDB is supported; mmCIF requires another tool.",
        ],
    }


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_owned(path: Path, identity: tuple[int, int]) -> bool:
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def _unlink_owned(path: Path, identity: tuple[int, int]) -> bool:
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return True
    if (current.st_dev, current.st_ino) != identity:
        return False
    os.unlink(path)
    return True


def _rollback_owned(parent: Path, identity: tuple[int, int], paths: tuple[Path, ...]) -> None:
    failures: list[str] = []
    for path in paths:
        try:
            if not _unlink_owned(path, identity):
                failures.append(f"{path.name}:identity-mismatch")
        except OSError as exc:
            failures.append(f"{path.name}:{exc.__class__.__name__}")
    try:
        fsync_directory(parent)
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


def safe_output_target(raw_path: str | Path, root: Path | None = None) -> Path:
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
    resolved_root = lexical_root.resolve(strict=True)
    if supplied.is_absolute():
        try:
            candidate = resolved_root / supplied.relative_to(lexical_root)
        except ValueError:
            candidate = supplied
    else:
        candidate = resolved_root / supplied
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ContractError(
            "output-outside-root",
            "output must remain under the current working directory",
            path=str(candidate),
        ) from exc
    if not relative.parts:
        raise ContractError("output-not-file", "output must name a file", path=str(candidate))

    cursor = resolved_root
    for part in relative.parts[:-1]:
        cursor /= part
        try:
            parent_state = os.lstat(cursor)
        except FileNotFoundError as exc:
            raise ContractError("output-parent-missing", "output parent must already exist", path=str(cursor)) from exc
        if stat.S_ISLNK(parent_state.st_mode):
            raise ContractError("output-parent-symlink", "output parent contains a symlink", path=str(cursor))
        if not stat.S_ISDIR(parent_state.st_mode):
            raise ContractError("unsafe-output-parent", "output parent must be a directory", path=str(cursor))
    try:
        os.lstat(candidate)
    except FileNotFoundError:
        pass
    else:
        raise ContractError("output-exists", "output exists; overwrite is forbidden", path=str(candidate))
    return candidate


def write_new_json(
    raw_path: str | Path,
    report: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    target = safe_output_target(raw_path, root)

    payload = (
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    temporary = Path(temporary_name)
    identity: tuple[int, int] | None = None
    published = False
    try:
        try:
            opened = os.fstat(descriptor)
        except OSError:
            opened = os.lstat(temporary)
        identity = (opened.st_dev, opened.st_ino)
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        try:
            os.close(descriptor)
        finally:
            descriptor = -1
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise ContractError("output-exists", "output appeared; overwrite is forbidden", path=str(target)) from exc
        published = True
        if not _is_owned(target, identity):
            raise OSError("published output identity differs from staged data")
        if not _unlink_owned(temporary, identity):
            raise OSError("temporary output identity changed after publication")
        fsync_directory(target.parent)
        if not _is_owned(target, identity):
            raise OSError("published output identity changed before completion")
    except BaseException as original:
        close_error: OSError | None = None
        if identity is None and descriptor >= 0:
            try:
                opened = os.fstat(descriptor)
                identity = (opened.st_dev, opened.st_ino)
            except OSError:
                pass
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                close_error = exc
        if identity is None:
            raise OSError("publication rollback failed: temporary identity unavailable") from original
        paths = (target, temporary) if published else (temporary,)
        try:
            _rollback_owned(target.parent, identity, paths)
        except OSError as rollback_error:
            raise rollback_error from original
        if close_error is not None:
            raise close_error from original
        raise
    return target


def pdb_atom(
    serial: int,
    atom: str,
    residue: str,
    chain: str,
    sequence: int,
    x: float,
    y: float,
    z: float,
    element: str,
    *,
    record: str = "ATOM",
    altloc: str = " ",
) -> str:
    return (
        f"{record:<6}{serial:>5} {atom:^4}{altloc}{residue:>3} {chain}{sequence:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}{1.0:>6.2f}{20.0:>6.2f}          {element:>2}\n"
    )


def expect_error(code: str, action: Any) -> None:
    try:
        action()
    except ContractError as exc:
        if exc.code != code:
            raise RuntimeError(f"expected {code}, got {exc.code}") from exc
    else:
        raise RuntimeError(f"expected {code}")


def expect_os_error(fragment: str, action: Any) -> None:
    try:
        action()
    except OSError as exc:
        if fragment not in str(exc):
            raise RuntimeError(f"expected OSError containing {fragment!r}, got {exc!r}") from exc
    else:
        raise RuntimeError(f"expected OSError containing {fragment!r}")


@contextmanager
def patched_os(name: str, replacement: Any) -> Iterator[None]:
    original = getattr(os, name)
    setattr(os, name, replacement)
    try:
        yield
    finally:
        setattr(os, name, original)


def require_test(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def self_test() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="bio02-interface-contacts-") as temporary:
        root = Path(temporary)
        structure = root / "tiny.pdb"
        structure.write_text(
            pdb_atom(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C")
            + pdb_atom(2, "H", "ALA", "A", 1, 3.0, 4.0, 0.0, "H")
            + pdb_atom(3, "CA", "GLY", "A", 2, 20.0, 0.0, 0.0, "C")
            + pdb_atom(4, "CA", "GLY", "B", 5, 3.0, 4.0, 0.0, "C")
            + pdb_atom(5, "C1", "LIG", "B", 6, 20.0, 0.0, 3.0, "C", record="HETATM")
            + "END\n",
            encoding="ascii",
        )
        report = build_report(str(structure), "A", "B", 5.0)
        require_test(report["summary"]["contact_count"] == 2, "contact count differs")
        require_test(
            [contact["minimum_distance_angstrom"] for contact in report["contacts"]] == [5.0, 3.0],
            "minimum distances or deterministic order differ",
        )
        require_test(
            report["contacts"][1]["residue_b"]["record_types"] == ["HETATM"],
            "HETATM residue was not retained",
        )
        require_test(report == build_report(str(structure), "A", "B", 5.0), "report is not deterministic")
        checks += 4

        output = root / "report.json"
        write_new_json(output, report, root=root)
        require_test(json.loads(output.read_text(encoding="utf-8")) == report, "published JSON differs")
        second_output = root / "report-copy.json"
        write_new_json(second_output, report, root=root)
        require_test(output.read_bytes() == second_output.read_bytes(), "JSON bytes are not deterministic")
        expect_error("output-exists", lambda: write_new_json(output, report, root=root))
        checks += 3

        zero_output = root / "zero.json"
        with patched_os("write", lambda _descriptor, _payload: 0):
            expect_os_error("no progress", lambda: write_new_json(zero_output, report, root=root))
        require_test(not zero_output.exists(), "zero-write publication left a final output")
        require_test(not list(root.glob(".zero.json.tmp-*")), "zero-write publication left a temporary output")
        checks += 2

        original_write = os.write

        def short_write(descriptor: int, payload: bytes) -> int:
            return original_write(descriptor, payload[:max(1, len(payload) // 3)])

        short_output = root / "short.json"
        with patched_os("write", short_write):
            write_new_json(short_output, report, root=root)
        require_test(short_output.read_bytes() == output.read_bytes(), "short writes truncated the output")
        checks += 1

        final_output = root / "final-identity.json"
        original_unlink = os.unlink
        swapped = False

        def replace_final_during_cleanup(path: str | os.PathLike[str]) -> None:
            nonlocal swapped
            if not swapped and os.path.basename(os.fspath(path)).startswith(".final-identity.json.tmp-"):
                swapped = True
                original_unlink(final_output)
                replacement = os.open(final_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    _write_all(replacement, b"competitor\n")
                    os.fsync(replacement)
                finally:
                    os.close(replacement)
            original_unlink(path)

        with patched_os("unlink", replace_final_during_cleanup):
            expect_os_error(
                "publication rollback failed",
                lambda: write_new_json(final_output, report, root=root),
            )
        require_test(final_output.read_bytes() == b"competitor\n", "rollback removed a replacement output")
        require_test(not list(root.glob(".final-identity.json.tmp-*")), "final identity check left a temporary output")
        final_output.unlink()
        checks += 2

        expect_error(
            "parent-traversal",
            lambda: write_new_json(Path("..") / "escape.json", report, root=root),
        )
        expect_error(
            "output-outside-root",
            lambda: write_new_json(root.parent / "outside.json", report, root=root),
        )
        checks += 2

        real_parent = root / "real-parent"
        real_parent.mkdir()
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        expect_error(
            "output-parent-symlink",
            lambda: write_new_json(linked_parent / "report.json", report, root=root),
        )
        checks += 1

        expect_error("same-chain", lambda: build_report(str(structure), "A", "A", 5.0))
        expect_error("invalid-cutoff", lambda: build_report(str(structure), "A", "B", math.nan))
        checks += 2

        altloc = root / "altloc.pdb"
        altloc.write_text(
            pdb_atom(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C", altloc="A")
            + pdb_atom(2, "CA", "GLY", "B", 1, 1.0, 0.0, 0.0, "C"),
            encoding="ascii",
        )
        expect_error(
            "alternate-location-unsupported",
            lambda: build_report(str(altloc), "A", "B", 5.0),
        )
        checks += 1

        models = root / "models.pdb"
        models.write_text(
            "MODEL        1\n"
            + pdb_atom(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C")
            + pdb_atom(2, "CA", "GLY", "B", 1, 1.0, 0.0, 0.0, "C")
            + "ENDMDL\nMODEL        2\nENDMDL\n",
            encoding="ascii",
        )
        expect_error("multiple-models-unsupported", lambda: build_report(str(models), "A", "B", 5.0))
        checks += 1

        atoms_a, atoms_b, _ = parse_pdb(str(structure), "A", "B")
        expect_error(
            "pair-cap-exceeded",
            lambda: find_contacts(atoms_a, atoms_b, 5.0, max_pair_comparisons=1),
        )
        checks += 1

        if hasattr(os, "symlink"):
            link = root / "input-link.pdb"
            link.symlink_to(structure)
            expect_error("symlink-refused", lambda: build_report(str(link), "A", "B", 5.0))
            checks += 1

    print(json.dumps({"checks": checks, "status": "pass", "version": VERSION}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Report bounded heavy-atom residue contacts between two legacy-PDB chains."
    )
    command.add_argument("--input")
    command.add_argument("--chain-a")
    command.add_argument("--chain-b")
    command.add_argument("--cutoff", type=float)
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
        name
        for name in ("input", "chain_a", "chain_b", "cutoff", "output")
        if getattr(args, name) is None
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
        report = build_report(args.input, args.chain_a, args.chain_b, args.cutoff)
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
