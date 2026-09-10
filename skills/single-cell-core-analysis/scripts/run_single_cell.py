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
        description="Small RNA Scanpy baseline using a matching QC receipt."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--input")
    p.add_argument("--qc-report")
    p.add_argument("--output")
    p.add_argument("--counts-layer")
    p.add_argument("--sample-column", default="sample_id")
    p.add_argument("--hvg", type=int, default=2000)
    p.add_argument("--pcs", type=int, default=30)
    p.add_argument("--neighbors", type=int, default=15)
    p.add_argument("--resolution", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--marker-count", type=int, default=20)
    a = p.parse_args()
    if a.self_test:
        return {"status": "pass", "version": VERSION, "checks": base_checks()}
    require(
        a.input and a.qc_report and a.output and a.counts_layer,
        "missing-contract",
        "Provide checked object, matching QC report, counts layer and new output.",
        "needs-decision",
    )
    require(
        2 <= a.hvg <= 30000
        and 2 <= a.pcs <= 100
        and 2 <= a.neighbors <= 100
        and 0 < a.resolution <= 5
        and 0 <= a.seed < 2**32
        and 1 <= a.marker_count <= 100,
        "settings",
        "Use bounded dimensions, graph settings, marker count and seed.",
    )
    obj, counts, digest = load_counts(a.input, a.counts_layer, a.sample_column)
    receipt = parse_json(read_local(a.qc_report))
    require(
        receipt.get("tool", {}).get("name") == "goose_single_cell_qc"
        and receipt.get("status") == "completed"
        and receipt.get("output_object_sha256") == digest
        and receipt.get("config", {}).get("counts_layer") == a.counts_layer
        and receipt["config"].get("sample_column") == a.sample_column,
        "qc-handoff",
        "QC report must describe this exact checked object and declared counts layer/sample column.",
    )
    try:
        import scanpy as sc
        import numpy as np
        from scipy import sparse
        from importlib.metadata import version
    except ImportError as exc:
        raise UserError(
            "missing-dependency",
            "Install the declared Scanpy and igraph adapter.",
            "needs-tool",
        ) from exc
    require(
        obj.n_obs >= 5 and obj.n_vars >= 5,
        "dimensions",
        "Use at least five retained cells and features for this exploratory baseline.",
    )
    require(
        "goose_cluster" not in obj.obs and "goose_cluster" not in obj.uns,
        "existing-analysis",
        "Use the QC input before this baseline; existing Goose analysis fields are preserved by refusing replacement.",
    )
    obj.X = counts.astype(float).copy()
    sc.pp.normalize_total(obj, target_sum=10000)
    sc.pp.log1p(obj)
    n_hvg = min(a.hvg, obj.n_vars)
    sc.pp.highly_variable_genes(obj, n_top_genes=n_hvg, flavor="seurat", subset=False)
    n_pcs = min(a.pcs, obj.n_obs - 1, int(obj.var["highly_variable"].sum()) - 1)
    require(
        n_pcs >= 2,
        "hvg-dimensions",
        "Too few variable features remain for PCA; inspect the input.",
    )
    sc.pp.pca(
        obj,
        n_comps=n_pcs,
        mask_var="highly_variable",
        svd_solver="arpack",
        random_state=a.seed,
    )
    neighbors = min(a.neighbors, obj.n_obs - 1)
    sc.pp.neighbors(
        obj,
        n_neighbors=neighbors,
        n_pcs=n_pcs,
        use_rep="X_pca",
        transformer="sklearn",
        random_state=a.seed,
    )
    sc.tl.umap(obj, random_state=a.seed, init_pos="random")
    sc.tl.leiden(
        obj,
        resolution=a.resolution,
        flavor="igraph",
        directed=False,
        n_iterations=2,
        random_state=a.seed,
        key_added="goose_cluster",
    )
    groups = obj.obs["goose_cluster"].value_counts()
    markers = []
    warnings = []
    if len(groups) < 2 or int(groups.min()) < 2:
        warnings.append(
            "Markers skipped: at least two clusters with two cells each are required."
        )
    else:
        sc.tl.rank_genes_groups(
            obj,
            "goose_cluster",
            method="wilcoxon",
            use_raw=False,
            n_genes=min(a.marker_count, obj.n_vars),
            tie_correct=True,
            pts=True,
        )
        for group in sorted(groups.index):
            df = sc.get.rank_genes_groups_df(obj, group=str(group))
            mask = np.asarray(obj.obs["goose_cluster"] == group)
            for _, r in df.iterrows():
                idx = obj.var_names.get_loc(r["names"])
                vals = obj.X[mask, idx]
                other = obj.X[~mask, idx]
                mean = float(vals.mean())
                fraction = float((vals > 0).sum() / mask.sum())
                outside = float((other > 0).sum() / (~mask).sum())
                markers.append(
                    [
                        str(group),
                        str(r["names"]),
                        float(r["scores"]),
                        float(r["pvals_adj"]),
                        mean,
                        fraction,
                        outside,
                    ]
                )
    raw = object_bytes(obj)
    config = {
        "counts_layer": a.counts_layer,
        "sample_column": a.sample_column,
        "normalization": "counts per 10000 then log1p",
        "hvg_flavor": "seurat",
        "hvg_requested": a.hvg,
        "hvg_actual": int(obj.var["highly_variable"].sum()),
        "pcs_requested": a.pcs,
        "pcs_actual": n_pcs,
        "neighbors_actual": neighbors,
        "neighbor_backend": "sklearn",
        "umap_init": "random",
        "leiden_flavor": "igraph",
        "leiden_iterations": 2,
        "resolution": a.resolution,
        "seed": a.seed,
        "marker_method": "wilcoxon exploratory cluster-vs-rest",
        "marker_count": a.marker_count,
    }
    report = report_base(
        "goose_single_cell_core",
        config,
        {
            "object": digest,
            "qc_report": hashlib.sha256(read_local(a.qc_report)).hexdigest(),
        },
    )
    report.update(
        cells=obj.n_obs,
        genes=obj.n_vars,
        clusters={str(k): int(v) for k, v in groups.items()},
        marker_rows=len(markers),
        warnings=warnings,
        versions={
            **sc_versions(),
            "scanpy": version("scanpy"),
            "igraph": version("igraph"),
        },
        output_object_sha256=hashlib.sha256(raw).hexdigest(),
    )
    report["limitations"] = [
        "Clusters and cluster-vs-rest markers are exploratory descriptions of the same data used to cluster; adjusted p-values are not independent confirmatory evidence.",
        "No batch integration, automatic annotation or condition-level inference. A fixed seed does not establish biological robustness.",
    ]
    embedding = [
        [
            str(cell),
            str(obj.obs.iloc[i][a.sample_column]),
            str(obj.obs.iloc[i]["goose_cluster"]),
            float(obj.obsm["X_umap"][i, 0]),
            float(obj.obsm["X_umap"][i, 1]),
        ]
        for i, cell in enumerate(obj.obs_names)
    ]
    new_bundle(
        a.output,
        {
            "processed.h5ad": raw,
            "embedding.tsv": table_bytes(
                ["cell_id", "sample_id", "cluster", "UMAP1", "UMAP2"], embedding
            ),
            "markers.tsv": table_bytes(
                [
                    "cluster",
                    "gene_id",
                    "score",
                    "padj",
                    "mean_expression",
                    "fraction_expressing",
                    "fraction_outside",
                ],
                markers,
            ),
            "analysis.json": encoded(report),
        },
    )
    return {
        "status": "completed",
        "clusters": len(groups),
        "marker_rows": len(markers),
        "version": VERSION,
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix=".goose-sc-cache-", dir=Path.cwd()) as cache:
        for variable in ["MPLCONFIGDIR", "XDG_CACHE_HOME", "NUMBA_CACHE_DIR"]:
            os.environ[variable] = cache
        raise SystemExit(cli(main))
