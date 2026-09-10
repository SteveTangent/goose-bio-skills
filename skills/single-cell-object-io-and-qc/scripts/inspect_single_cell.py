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


def load_counts(path, layer, sample_column):
    try:
        import numpy as np
        import anndata as ad
        import h5py
        from scipy import sparse
    except ImportError as exc:
        raise UserError(
            "missing-dependency",
            "Install the declared AnnData, SciPy and h5py adapter.",
            "needs-tool",
        ) from exc
    raw = read_local(path)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "input.h5ad"
        staged.write_bytes(raw)
        with h5py.File(staged, "r") as handle:
            total = [0]
            visited = set()

            def inspect(group):
                address = h5py.h5o.get_info(group.id).addr
                require(
                    address not in visited,
                    "hdf-cycle",
                    "Repeated HDF5 group links are unsupported.",
                )
                visited.add(address)
                for key in group:
                    require(
                        isinstance(group.get(key, getlink=True), h5py.HardLink),
                        "hdf-link",
                        "External and soft HDF5 links are unsupported.",
                    )
                    item = group[key]
                    if isinstance(item, h5py.Group):
                        inspect(item)
                    else:
                        total[0] += (
                            math.prod(item.shape) if item.shape is not None else 0
                        )
                        require(
                            total[0] <= 10000000,
                            "object-size",
                            "Use a small object with at most ten million stored elements.",
                        )

            inspect(handle)
        obj = ad.read_h5ad(staged)
    require(
        obj.obs_names.is_unique and obj.var_names.is_unique,
        "duplicate-id",
        "Cell and feature IDs must be unique.",
    )
    require(
        3 <= obj.n_obs <= 5000
        and 2 <= obj.n_vars <= 30000
        and obj.n_obs * obj.n_vars <= 10000000,
        "object-size",
        "This local adapter supports 3–5,000 cells and at most ten million cell-feature entries.",
    )
    for v in list(obj.obs_names) + list(obj.var_names):
        identity(str(v))
    require(
        layer in obj.layers,
        "counts-layer",
        "Provide an explicitly named layer containing authoritative raw counts.",
        "needs-decision",
    )
    require(
        sample_column in obj.obs,
        "sample-column",
        "Provide a biological sample column.",
        "needs-decision",
    )
    require(
        not obj.obs[sample_column].isna().any(),
        "sample-missing",
        "Biological sample IDs must be complete.",
    )
    for v in obj.obs[sample_column]:
        identity(str(v))
        require(
            str(v) not in {"NA", "unknown", ""},
            "sample-missing",
            "Declare biological samples.",
        )
    counts = obj.layers[layer]
    require(
        sparse.issparse(counts) or isinstance(counts, np.ndarray),
        "matrix-type",
        "Use an in-memory dense or sparse counts layer.",
    )
    values = counts.data if sparse.issparse(counts) else counts
    require(
        np.isfinite(values).all()
        and (values >= 0).all()
        and (values <= 2**31 - 1).all()
        and np.equal(values, np.floor(values)).all(),
        "raw-counts",
        "Counts must be finite nonnegative integers; numeric appearance does not prove provenance.",
    )
    return obj, counts, hashlib.sha256(raw).hexdigest()


def object_bytes(obj):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "output.h5ad"
        obj.write_h5ad(path, compression="gzip")
        raw = path.read_bytes()
    require(
        len(raw) <= 8 * 1024 * 1024,
        "output-size",
        "The serialized object exceeds the small-object handoff limit.",
    )
    return raw


def sc_versions():
    from importlib.metadata import version

    return {name: version(name) for name in ["numpy", "scipy", "anndata", "h5py"]}


VERSION = "0.11.0"


def main():
    p = argparse.ArgumentParser(
        description="Inspect/filter a small declared raw-count h5ad without modifying inputs."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--counts-layer")
    p.add_argument("--sample-column", default="sample_id")
    p.add_argument("--assay")
    p.add_argument("--min-counts", type=int)
    p.add_argument("--min-genes", type=int)
    p.add_argument("--mitochondrial-prefix")
    p.add_argument("--max-mito-fraction", type=float)
    a = p.parse_args()
    if a.self_test:
        return {"status": "pass", "version": VERSION, "checks": base_checks()}
    require(
        a.input and a.output and a.counts_layer and a.assay,
        "missing-contract",
        "Declare input, new output, counts layer and assay.",
        "needs-decision",
    )
    require(
        a.assay == "rna", "unsupported-assay", "This adapter supports RNA counts only."
    )
    require(
        a.min_counts is not None and a.min_genes is not None,
        "qc-thresholds",
        "Declare minimum count and gene thresholds; zero explicitly means no filter for that metric.",
        "needs-decision",
    )
    require(
        a.min_counts >= 0 and a.min_genes >= 0,
        "threshold",
        "Thresholds must be nonnegative.",
    )
    require(
        a.max_mito_fraction is None
        or (a.mitochondrial_prefix and 0 <= a.max_mito_fraction <= 1),
        "mito-contract",
        "A mitochondrial filter requires an explicit matching feature prefix and a fraction from zero to one.",
    )
    obj, counts, digest = load_counts(a.input, a.counts_layer, a.sample_column)
    import numpy as np

    totals = np.asarray(counts.sum(axis=1)).ravel()
    genes = np.asarray((counts > 0).sum(axis=1)).ravel()
    mito = None
    if a.mitochondrial_prefix:
        mask = np.array(
            [str(g).startswith(a.mitochondrial_prefix) for g in obj.var_names]
        )
        require(
            mask.any(),
            "mito-prefix",
            "The declared mitochondrial prefix matches no features; confirm species and identifier namespace.",
            "needs-decision",
        )
        mito = np.divide(
            np.asarray(counts[:, mask].sum(axis=1)).ravel(),
            totals,
            out=np.zeros_like(totals, dtype=float),
            where=totals > 0,
        )
    keep = (totals >= a.min_counts) & (genes >= a.min_genes) & (totals > 0)
    if a.max_mito_fraction is not None:
        keep &= mito <= a.max_mito_fraction
    require(
        int(keep.sum()) >= 3,
        "too-few-cells",
        "Fewer than three nonzero cells remain; inspect QC choices.",
    )
    rows = []
    for i, cell in enumerate(obj.obs_names):
        reasons = []
        if totals[i] == 0:
            reasons.append("zero-counts")
        if totals[i] < a.min_counts:
            reasons.append("low-counts")
        if genes[i] < a.min_genes:
            reasons.append("low-genes")
        if a.max_mito_fraction is not None and mito[i] > a.max_mito_fraction:
            reasons.append("high-mito-fraction")
        rows.append(
            [
                cell,
                str(obj.obs.iloc[i][a.sample_column]),
                int(totals[i]),
                int(genes[i]),
                "" if mito is None else float(mito[i]),
                str(bool(keep[i])).lower(),
                ";".join(reasons),
            ]
        )
    raw = object_bytes(obj[keep].copy())
    report = report_base(
        "goose_single_cell_qc",
        {
            "counts_layer": a.counts_layer,
            "sample_column": a.sample_column,
            "assay": a.assay,
            "min_counts": a.min_counts,
            "min_genes": a.min_genes,
            "mitochondrial_prefix": a.mitochondrial_prefix,
            "max_mito_fraction": a.max_mito_fraction,
        },
        {"object": digest},
    )
    report.update(
        cells_input=obj.n_obs,
        cells_retained=int(keep.sum()),
        genes=obj.n_vars,
        output_object_sha256=hashlib.sha256(raw).hexdigest(),
        versions=sc_versions(),
    )
    report["limitations"] = [
        "No doublet detection, ambient-RNA correction or automatic QC cutoffs. Thresholds need biological review.",
        "Raw-count provenance and sample identity are user declarations. No assay conversion or batch integration.",
    ]
    new_bundle(
        a.output,
        {
            "checked.h5ad": raw,
            "qc.tsv": table_bytes(
                [
                    "cell_id",
                    "sample_id",
                    "total_counts",
                    "detected_genes",
                    "mito_fraction",
                    "retained",
                    "reasons",
                ],
                rows,
            ),
            "qc.json": encoded(report),
        },
    )
    return {
        "status": "completed",
        "cells_retained": int(keep.sum()),
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
