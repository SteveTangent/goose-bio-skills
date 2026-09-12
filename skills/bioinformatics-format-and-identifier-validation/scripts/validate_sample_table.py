#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Original, embedded I/O boundary: each exported helper remains standalone.
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_BYTES = 8 * 1024 * 1024


class UserError(ValueError):
    def __init__(self, code, message, status="invalid-input"):
        self.code, self.status = code, status
        super().__init__(message)


def require(condition, code, message, status="invalid-input"):
    if not condition:
        raise UserError(code, message, status)


def local_path(value):
    path = Path(value)
    root = Path.cwd().resolve()
    require(
        ".." not in path.parts,
        "parent-traversal",
        "Use a path within the working directory.",
    )
    path = path if path.is_absolute() else root / path
    require(
        path != root and path.is_relative_to(root),
        "outside-workspace",
        "Use a file or new output directory inside the working directory.",
    )
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        require(
            not current.is_symlink(), "symlink-path", "Symlink paths are not accepted."
        )
    require(
        path.parent.is_dir(),
        "missing-parent",
        "Create the output parent directory first.",
    )
    return path


def read_local(value):
    path = local_path(value)
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
            "input-size-or-type",
            "Use a regular file of at most 8 MiB.",
        )
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    require(
        len(data) <= MAX_BYTES
        and (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns),
        "input-changed",
        "The input changed or exceeded its size limit.",
    )
    return data


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(
                key not in result, "duplicate-json-key", "JSON keys must be unique."
            )
            result[key] = value
        return result

    try:
        return json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, UserError):
            raise
        raise UserError("invalid-json", "Use finite, valid UTF-8 JSON.") from exc


def read_json(value):
    data = read_local(value)
    return parse_json(data), hashlib.sha256(data).hexdigest()


def tsv(data):
    try:
        rows = list(
            csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("invalid-tsv", "Use a UTF-8 tab-separated table.") from exc
    require(
        len(rows) >= 2 and len(rows[0]) == len(set(rows[0])),
        "table-header",
        "A unique header and data rows are required.",
    )
    require(
        all(len(row) == len(rows[0]) for row in rows),
        "table-shape",
        "Every row must match the header.",
    )
    require(
        all(
            cell and len(cell) <= 256 and not any(ord(c) < 32 for c in cell)
            for row in rows
            for cell in row
        ),
        "table-cell",
        "Empty, oversized or control-character fields are not accepted.",
    )
    return rows


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


def new_file(value, data):
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output path; existing files are preserved.",
        "invalid-output",
    )
    require(
        len(data) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds the bounded size.",
        "invalid-output",
    )
    fd, stage = tempfile.mkstemp(prefix=".goose-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(stage, path, follow_symlinks=False)
    finally:
        os.unlink(stage)


def new_bundle(value, files):
    """Reserve a new directory exclusively; rollback only files we created."""
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output directory.",
        "invalid-output",
    )
    require(
        files
        and all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name) for name in files
        ),
        "bundle-names",
        "Invalid output member.",
        "invalid-output",
    )
    require(
        sum(map(len, files.values())) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds 64 MiB.",
        "invalid-output",
    )
    created = []
    with tempfile.TemporaryDirectory(prefix=".goose-stage-", dir=path.parent) as stage:
        for name, data in files.items():
            with (Path(stage) / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        path.mkdir(mode=0o700, exist_ok=False)
        directory_id = path.stat().st_ino
        try:
            for name in files:
                target = path / name
                os.link(Path(stage) / name, target, follow_symlinks=False)
                created.append((target, target.stat().st_ino))
        except BaseException:
            if not path.is_symlink() and path.stat().st_ino == directory_id:
                for target, identity in created:
                    if (
                        not target.is_symlink()
                        and target.exists()
                        and target.stat().st_ino == identity
                    ):
                        target.unlink()
                try:
                    path.rmdir()
                except OSError:
                    pass
            raise


def base_checks():
    old = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            new_file("a.json", encoded({"value": 1}))
            before = Path("a.json").read_bytes()
            try:
                new_file("a.json", b"changed")
            except UserError:
                pass
            else:
                raise AssertionError("overwrite accepted")
            assert Path("a.json").read_bytes() == before
            Path("link").symlink_to("a.json")
            for path in ["link", "../outside"]:
                try:
                    read_local(path)
                except UserError:
                    pass
                else:
                    raise AssertionError("unsafe path accepted")
            for payload in [b'{"a":1,"a":2}', b'{"a":NaN}']:
                try:
                    parse_json(payload)
                except UserError:
                    pass
                else:
                    raise AssertionError("invalid JSON accepted")
            new_bundle("bundle", {"a.txt": b"a", "b.txt": b"b"})
            try:
                new_bundle("bundle", {"a.txt": b"changed"})
            except UserError:
                pass
            else:
                raise AssertionError("bundle overwritten")
            assert (Path("bundle") / "a.txt").read_bytes() == b"a"
        finally:
            os.chdir(old)
    return 6


def cli(run):
    try:
        result = run()
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except UserError as exc:
        print(
            json.dumps(
                {
                    "status": exc.status,
                    "code": exc.code,
                    "message": str(exc),
                    "analysis_completed": False,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid-input",
                    "code": "unsupported-record-schema",
                    "message": "Check the input record shape and declared adapter version.",
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "io-error",
                    "code": type(exc).__name__,
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 3


# Explicit tabular contracts shared at authoring time; each export is standalone.
def read_table(path):
    raw = read_local(path)
    try:
        rows = list(
            csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("invalid-tsv", "Use a UTF-8 TSV with a header.") from exc
    require(
        len(rows) >= 2
        and rows[0]
        and all(rows[0])
        and len(set(rows[0])) == len(rows[0]),
        "table-header",
        "Use unique nonempty columns and data rows.",
    )
    require(
        len(rows) <= 100001 and all(len(r) == len(rows[0]) for r in rows),
        "table-shape",
        "Use a bounded rectangular table.",
    )
    require(
        all(
            len(v) <= 1024 and not any(ord(c) < 32 for c in v) for r in rows for v in r
        ),
        "table-cell",
        "Table cells must be bounded single-line values.",
    )
    return (
        rows[0],
        [dict(zip(rows[0], r)) for r in rows[1:]],
        hashlib.sha256(raw).hexdigest(),
    )


def fields(header, names):
    require(
        all(n in header for n in names) and len(names) == len(set(names)),
        "columns",
        "Declare distinct existing input columns.",
    )


def finite(value):
    require(not isinstance(value, bool), "number", "Use finite numeric values.")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise UserError("number", "Use finite numeric values.") from exc
    require(math.isfinite(result), "number", "Non-finite values are not measurements.")
    return result


def identity(value):
    require(
        isinstance(value, str)
        and 0 < len(value) <= 128
        and not any(ord(c) < 32 for c in value),
        "identifier",
        "Use nonempty, unique, bounded identifiers.",
    )
    return value


def table_bytes(header, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def report_base(name, config, hashes):
    return {
        "schema_version": "1.0",
        "status": "completed",
        "tool": {"name": name, "version": VERSION},
        "config": config,
        "input_sha256": hashes,
        "network_performed": False,
        "limitations": [],
    }


VERSION = "0.12.0"


def main():
    p = argparse.ArgumentParser(
        description="Validate an explicit sample table, optionally align it to a bounded matrix."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--metadata")
    p.add_argument("--matrix")
    p.add_argument("--output")
    p.add_argument("--sample-column", default="sample_id")
    p.add_argument("--group-column")
    p.add_argument("--subject-column")
    p.add_argument("--batch-column")
    p.add_argument("--rename", action="append", default=[])
    p.add_argument("--design", choices=["independent", "paired", "unknown"], default="unknown")
    p.add_argument("--numerator")
    p.add_argument("--denominator")
    p.add_argument("--matrix-scale", choices=["raw-counts", "log2-normalized", "continuous", "unknown"])
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        try:
            fields(["a", "b"], ["a", "a"])
        except UserError:
            pass
        else:
            raise AssertionError("duplicate column mapping accepted")
        return {"status": "pass", "version": VERSION, "checks": count + 1}
    require(
        a.metadata and a.output,
        "missing-contract",
        "Provide metadata and a new output directory.",
        "needs-decision",
    )
    header, rows, digest = read_table(a.metadata)
    mapping = {}
    for item in a.rename:
        require("=" in item, "rename", "Use explicit OLD=NEW renames.")
        old, new = item.split("=", 1)
        require(
            old in header and old not in mapping and new,
            "rename",
            "Rename only existing unique columns.",
        )
        mapping[old] = identity(new)
    new_header = [mapping.get(c, c) for c in header]
    require(
        len(set(new_header)) == len(new_header),
        "rename-collision",
        "Renaming would create duplicate columns.",
    )
    rows = [{mapping.get(k, k): v for k, v in r.items()} for r in rows]
    header = new_header
    required = [a.sample_column] + [
        v for v in [a.group_column, a.subject_column, a.batch_column] if v
    ]
    fields(header, required)
    require(1 <= len(rows) <= 5000, "sample-count", "Use up to 5,000 sample records.")
    ids = [identity(r[a.sample_column]) for r in rows]
    require(
        len(set(ids)) == len(ids),
        "duplicate-sample",
        "Sample identifiers must be unique.",
    )
    hashes = {"metadata": digest}
    matrix_summary = None
    if a.matrix:
        require(
            a.matrix_scale,
            "matrix-scale",
            "Declare the matrix scale; unknown is accepted for inspection only.",
            "needs-decision",
        )
        mh, mr, mdigest = read_table(a.matrix)
        require(
            len(mh) >= 2 and len(mr) <= 30000,
            "matrix-size",
            "Use a feature-by-sample matrix with at most 30,000 feature rows.",
        )
        features = [identity(r[mh[0]]) for r in mr]
        require(
            len(set(features)) == len(features),
            "duplicate-feature",
            "Feature IDs must be unique.",
        )
        require(
            set(mh[1:]) == set(ids),
            "sample-mismatch",
            "Matrix columns and metadata IDs must match exactly; no samples are silently dropped.",
        )
        for r in mr:
            for c in mh[1:]:
                v = finite(r[c])
                require(
                    a.matrix_scale != "raw-counts"
                    or (v >= 0 and v.is_integer() and v <= 2**31 - 1),
                    "count-values",
                    "Declared raw counts require nonnegative signed-32-bit integer values; appearance does not prove provenance.",
                )
        lookup = {r[a.sample_column]: r for r in rows}
        rows = [lookup[s] for s in mh[1:]]
        hashes["matrix"] = mdigest
        matrix_summary = {
            "features": len(mr),
            "samples": len(ids),
            "declared_scale": a.matrix_scale,
            "sample_order": mh[1:],
        }
    unresolved = []
    warnings = []
    for c in required:
        missing = [r[a.sample_column] for r in rows if r[c].strip().lower() in {"", "na", "unknown", "nan", "null"}]
        if missing:
            unresolved.append(
                {"column": c, "sample_ids": missing, "reason": "missing-declared-fact"}
            )
    if a.subject_column:
        subjects = {}
        for r in rows:
            subjects.setdefault(r[a.subject_column], []).append(r[a.sample_column])
        repeated = {
            k: v
            for k, v in subjects.items()
            if len(v) > 1 and k not in {"", "NA", "unknown"}
        }
        if repeated:
            warnings.append(
                {
                    "code": "repeated-subject",
                    "units": repeated,
                    "message": "Repeated biological units require a suitable design; this check does not choose that model.",
                }
            )
    if a.group_column and a.batch_column and not unresolved:
        batches = {}
        for r in rows:
            batches.setdefault(r[a.batch_column], set()).add(r[a.group_column])
        if len({r[a.group_column] for r in rows}) > 1 and all(
            len(g) == 1 for g in batches.values()
        ):
            warnings.append(
                {
                    "code": "group-nested-in-batch",
                    "message": "Every batch contains only one condition. With fixed categorical batch terms, the condition cannot be separated; inspect the study design.",
                }
            )
    design = {"declared": a.design, "groups": {}, "batch_by_group": {}, "metadata_ready": False}
    if a.group_column:
        for r in rows:
            group=r[a.group_column]
            entry=design["groups"].setdefault(group,{"sample_rows":0,"declared_units":set()})
            entry["sample_rows"]+=1
            if a.subject_column and r[a.subject_column] not in {"", "NA", "unknown"}:
                entry["declared_units"].add(r[a.subject_column])
            if a.batch_column:
                d=design["batch_by_group"].setdefault(r[a.batch_column],{})
                d[group]=d.get(group,0)+1
        for entry in design["groups"].values():
            entry["declared_units"]=len(entry["declared_units"]) if a.subject_column else None
    if a.design != "unknown":
        if not a.subject_column or not a.group_column:
            unresolved.append("Declare subject and group columns for design screening.")
        elif not a.numerator or not a.denominator or a.numerator==a.denominator or set(design["groups"])!={a.numerator,a.denominator}:
            unresolved.append("Declare exactly two comparison levels and their direction.")
        elif any(x["declared_units"]<2 for x in design["groups"].values()):
            unresolved.append("At least two declared biological units per group are required for this bounded route; adequacy still needs review.")
        if a.design=="independent" and any(w["code"]=="repeated-subject" for w in warnings):
            unresolved.append("Repeated subjects conflict with an independent-sample model.")
        if a.design=="paired" and a.subject_column and a.group_column:
            pairs={}
            for r in rows: pairs.setdefault(r[a.subject_column],[]).append(r[a.group_column])
            if not a.numerator or not a.denominator or any(sorted(v)!=sorted([a.numerator,a.denominator]) for v in pairs.values()):
                unresolved.append("A paired design needs one record per subject per declared group.")
            design["paired_units"]=len(pairs)
            unresolved.append("Paired expression DE is outside the bundled expression models; retain the pairs for a suitable external model.")
        if a.matrix and a.matrix_scale=="unknown":
            unresolved.append("Confirm expression scale before model selection.")
        if any(w["code"]=="group-nested-in-batch" for w in warnings):
            unresolved.append("Condition is confounded with the recorded batch; do not assume batch adjustment can separate them.")
        if a.batch_column in {"sample_id", "condition", "subject_id"}:
            unresolved.append("Rename the adjustment column to avoid reserved downstream metadata headings.")
        design["metadata_ready"]=not unresolved
    extra={}
    if a.group_column and not any(r[a.group_column] in {"", "NA", "unknown"} for r in rows):
        extra["plot-groups.tsv"]=table_bytes(["sample_id","group"],[[r[a.sample_column],r[a.group_column]] for r in rows])
        if a.batch_column:
            extra["plot-batches.tsv"]=table_bytes(["sample_id","group"],[[r[a.sample_column],r[a.batch_column]] for r in rows])
    if design["metadata_ready"]:
        de_columns=[a.sample_column,a.group_column]+([a.batch_column] if a.batch_column else [])
        extra["count-de-samples.tsv"]=table_bytes(["sample_id","condition"]+([a.batch_column] if a.batch_column else []),[[r[k] for k in de_columns] for r in rows])
        micro_columns=[a.sample_column,a.group_column,a.subject_column]+([a.batch_column] if a.batch_column else [])
        extra["microarray-samples.tsv"]=table_bytes(["sample_id","condition","subject_id"]+([a.batch_column] if a.batch_column else []),[[r[k] for k in micro_columns] for r in rows])
    report = report_base(
        "goose_sample_validation", {"columns": required, "renames": mapping, "design": a.design, "numerator": a.numerator, "denominator": a.denominator, "matrix_scale": a.matrix_scale}, {**hashes}
    )
    report.update(
        samples=len(rows),
        design=design,
        files=["samples.tsv", "validation.json", *extra],
        output_sha256={k: hashlib.sha256(v).hexdigest() for k,v in extra.items()},
        matrix=matrix_summary,
        warnings=warnings,
        unresolved=unresolved,
    )
    if unresolved:
        report["status"] = "needs-decision"
    report["limitations"] = [
        "Inspection and ordering only; no biological groups, independent units, count provenance or model adequacy are inferred.",
        "File-name patterns never supply missing study facts. Explicit renames are recorded; inputs are unchanged.",
    ]
    new_bundle(
        a.output,
        {
            "samples.tsv": table_bytes(header, [[r[c] for c in header] for r in rows]),
            "validation.json": encoded(report),
            **extra,
        },
    )
    return {
        "status": report["status"],
        "samples": len(rows),
        "warnings": len(warnings),
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
