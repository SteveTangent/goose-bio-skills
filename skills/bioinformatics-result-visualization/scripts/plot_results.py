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


VERSION = "0.12.0"


def validate_de(report):
    require(
        isinstance(report, dict)
        and report.get("status") == "completed"
        and report.get("method") in {"DESeq2", "limma-microarray"},
        "de-report",
        "Use a completed Goose DESeq2 or microarray limma result; plotting does not fit a model.",
    )
    rows = report.get("model", {}).get("results")
    require(
        isinstance(rows, list)
        and rows
        and all(
            isinstance(x, dict) and isinstance(x.get("gene_id"), str) for x in rows
        ),
        "de-results",
        "The report has no gene result table.",
    )
    require(
        len(rows) <= 30000 and len({r["gene_id"] for r in rows}) == len(rows),
        "de-identities",
        "Gene IDs must be unique and bounded.",
    )
    return rows


def volcano_data(report, significance, alpha, effect):
    rows = validate_de(report)
    require(
        math.isfinite(alpha)
        and 0 < alpha < 1
        and math.isfinite(effect)
        and effect >= 0,
        "plot-thresholds",
        "Declare alpha and an absolute log2-fold-change threshold.",
    )
    data = []
    omitted = 0
    for row in rows:
        fc, pvalue = row.get("log2FoldChange"), row.get(significance)
        if fc is None or pvalue is None:
            omitted += 1
            continue
        require(
            all(
                isinstance(x, (int, float))
                and not isinstance(x, bool)
                and math.isfinite(x)
                for x in [fc, pvalue]
            )
            and 0 <= pvalue <= 1,
            "plot-values",
            "Effects and selected significance must be finite and in range.",
        )
        selected = pvalue <= alpha and abs(fc) >= effect
        category = ("positive" if fc >= 0 else "negative") if selected else "other"
        data.append(
            [row["gene_id"], fc, pvalue, -math.log10(max(pvalue, 1e-300)), category]
        )
    require(
        data,
        "no-plot-points",
        "No finite points remain for plotting.",
        "invalid-output",
    )
    return data, omitted


def matrix_data(args, de):
    if args.counts:
        require(
            de is not None,
            "counts-need-model",
            "Raw counts require the matching DE report and its recorded size factors.",
        )
        raw = read_local(args.counts)
        require(
            hashlib.sha256(raw).hexdigest() == de.get("input_sha256", {}).get("counts"),
            "counts-fingerprint",
            "Counts must exactly match the DE report input.",
        )
        table = tsv(raw)
        require(
            table[0][0] == "gene_id", "matrix-header", "Matrix must start with gene_id."
        )
        qc = de["model"].get("qc", {})
        samples = table[0][1:]
        factors = qc.get("size_factors")
        require(
            samples == qc.get("samples")
            and isinstance(factors, list)
            and len(factors) == len(samples)
            and all(
                isinstance(x, (int, float))
                and not isinstance(x, bool)
                and math.isfinite(x)
                and x > 0
                for x in factors
            ),
            "size-factors",
            "The DE size factors or sample order are invalid.",
        )
        retained = {r["gene_id"] for r in validate_de(de)}
        rows = [r for r in table[1:] if r[0] in retained]
        require(
            len(rows) == len(retained),
            "retained-genes",
            "Counts do not contain exactly the retained genes.",
        )
        data = []
        for row in rows:
            require(
                all(re.fullmatch(r"0|[1-9][0-9]*", x) is not None for x in row[1:]),
                "raw-counts",
                "Counts must be nonnegative integers.",
            )
            data.append(
                [math.log2(int(x) / factor + 1) for x, factor in zip(row[1:], factors)]
            )
        return (
            [r[0] for r in rows],
            samples,
            data,
            hashlib.sha256(raw).hexdigest(),
            "log2(DESeq2-normalized counts + 1)",
        )
    require(
        args.matrix and args.matrix_scale,
        "matrix-contract",
        "Provide an already transformed matrix and declare its scale, or matching counts plus a DE report.",
        "needs-decision",
    )
    raw = read_local(args.matrix)
    if de is not None and de.get("method") == "limma-microarray":
        require(hashlib.sha256(raw).hexdigest() == de.get("input_sha256", {}).get("expression") and args.matrix_scale == "log2-normalized", "expression-fingerprint", "Use the exact normalized log2 expression input of the microarray model.")
    table = tsv(raw)
    require(
        table[0][0] in {"gene_id", "feature_id"}, "matrix-header", "A transformed matrix must start with gene_id or feature_id."
    )
    try:
        data = [[float(x) for x in row[1:]] for row in table[1:]]
    except ValueError as exc:
        raise UserError("matrix-values", "Use a finite numeric matrix.") from exc
    require(
        all(math.isfinite(x) for row in data for x in row),
        "matrix-values",
        "Missing and non-finite matrix values need an explicit upstream decision.",
    )
    return (
        [r[0] for r in table[1:]],
        table[0][1:],
        data,
        hashlib.sha256(raw).hexdigest(),
        args.matrix_scale,
    )


def expansion_plot(a):
    require(
        a.result and a.output,
        "plot-input",
        "Provide a result JSON (or declared table) and a new output directory.",
        "needs-decision",
    )
    raw = read_local(a.result)
    report = None
    table = None
    if a.kind in {"generic-volcano", "embedding"}:
        table = list(csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t"))
        require(0 < len(table) <= 30000, "plot-table", "Use a nonempty bounded table.")
    else:
        report = parse_json(raw)
    expected = {
        "groups": "goose_two_group",
        "correlation": "goose_correlation",
        "concordance": "goose_result_concordance",
        "marker-dot": "goose_marker_evidence",
    }
    if report is not None:
        require(
            report.get("tool", {}).get("name") == expected[a.kind],
            "plot-source",
            "Choose the plot matching the declared helper result.",
        )
    with tempfile.TemporaryDirectory(prefix=".goose-plot-", dir=Path.cwd()) as tmp:
        os.environ["MPLCONFIGDIR"] = tmp
        os.environ["XDG_CACHE_HOME"] = tmp
        try:
            import numpy as np
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise UserError(
                "plot-dependencies", "Install NumPy and Matplotlib.", "needs-tool"
            ) from exc
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "text.usetex": False,
                "text.parse_math": False,
                "svg.hashsalt": "goose-bio-skills",
            }
        )
        fig, ax = plt.subplots(figsize=(9, 6), layout="constrained")
        notes = []
        rows = []
        config = {"kind": a.kind}
        title = a.title or a.kind.replace("-", " ").title()
        if a.kind == "groups":
            outcomes = sorted({r["outcome"] for r in report["results"]})
            selected = a.outcome or (outcomes[0] if len(outcomes) == 1 else None)
            require(
                selected in outcomes,
                "plot-outcome",
                "Select one outcome when the report contains several.",
                "needs-decision",
            )
            config["outcome"] = selected
            cfg = report["config"]
            labels = [cfg["denominator"], cfg["numerator"]]
            points = [r for r in report["points"] if r["outcome"] == selected]
            header = ["subject", "group", "value"]
            rows = [[r["subject_id"], r["group"], r["value"]] for r in points]
            for j, label in enumerate(labels):
                values = [r["value"] for r in points if r["group"] == label]
                ax.scatter(
                    [j] * len(values),
                    values,
                    s=40,
                    alpha=0.8,
                    color=["#2563eb", "#d97706"][j],
                )
            if cfg["method"] == "paired":
                subjects = sorted({r["subject_id"] for r in points})
                for subject in subjects:
                    ax.plot(
                        [0, 1],
                        [
                            next(
                                r["value"]
                                for r in points
                                if r["subject_id"] == subject and r["group"] == g
                            )
                            for g in labels
                        ],
                        color="#94a3b8",
                        alpha=0.5,
                        zorder=0,
                    )
            ax.set_xticks([0, 1], labels)
            ax.set_xlim(-0.5, 1.5)
            ax.set_ylabel(selected + " (" + cfg["unit"] + ")")
            r = next(r for r in report["results"] if r["outcome"] == selected)
            notes.append(
                f"Mean difference {r['mean_difference']:.3g}; {cfg['confidence']:.0%} CI [{r['ci_low']:.3g}, {r['ci_high']:.3g}]. {cfg['numerator']} minus {cfg['denominator']}. No multiplicity correction."
            )
        elif a.kind == "correlation":
            results = report["results"]
            selected = [
                r
                for r in results
                if (a.x_variable is None or r["x"] == a.x_variable)
                and (a.y_variable is None or r["y"] == a.y_variable)
            ]
            require(
                len(selected) == 1,
                "plot-pair",
                "Select one exact x/y pair.",
                "needs-decision",
            )
            r = selected[0]
            require(
                r["coefficient"] is not None,
                "undefined-pair",
                "A constant pair has no defined correlation.",
            )
            points = [
                p
                for p in report["points"]
                if p["x_variable"] == r["x"] and p["y_variable"] == r["y"]
            ]
            header = ["sample_id", r["x"], r["y"]]
            rows = [[p["sample_id"], p["x"], p["y"]] for p in points]
            ax.scatter(
                [p["x"] for p in points],
                [p["y"] for p in points],
                color="#2563eb",
                s=38,
                alpha=0.8,
            )
            ax.set_xlabel(r["x"])
            ax.set_ylabel(r["y"])
            notes.append(
                f"{report['config']['method']} coefficient {r['coefficient']:.3g}; complete n={r['n']}. Association is not causation."
            )
            config.update(x=r["x"], y=r["y"])
        elif a.kind == "concordance":
            labels = report["comparisons"]
            data = report["results"]
            limit = a.top_features or 40
            require(1 <= limit <= 50, "feature-limit", "Display at most 50 features.")
            data = data[:limit]
            states = ["not-present", "not-tested", "tested-not-selected", "selected"]
            colors = ["#f1f5f9", "#64748b", "#93c5fd", "#b45309"]
            matrix = [
                [states.index(r["membership"][g]["status"]) for g in labels]
                for r in data
            ]
            from matplotlib.colors import ListedColormap, BoundaryNorm

            im = ax.imshow(
                matrix,
                cmap=ListedColormap(colors),
                norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4),
                aspect="auto",
            )
            ax.set_xticks(range(len(labels)), labels)
            ax.set_yticks(range(len(data)), [r["feature_id"] for r in data], fontsize=7)
            fig.colorbar(im, ax=ax, ticks=range(4)).ax.set_yticklabels(states)
            header = ["feature_id", "comparison", "status"]
            rows = [
                [r["feature_id"], g, r["membership"][g]["status"]]
                for r in data
                for g in labels
            ]
            notes.append(
                f"First {len(data)} of {len(report['results'])} IDs in lexical order; display selection is not an evidence ranking."
            )
            config["display_limit"] = limit
        elif a.kind == "marker-dot":
            data = report["expression_measurements"]
            require(
                data,
                "missing-expression",
                "Marker evidence alone cannot provide expression intensity or fraction. Supply measured means and fractions.",
                "needs-decision",
            )
            genes = sorted({r["gene_id"] for r in data})
            clusters = sorted({r["cluster"] for r in data})
            require(
                len(genes) <= 40 and len(clusters) <= 20,
                "dotplot-size",
                "Provide at most 40 genes and 20 clusters for a legible dot plot.",
            )
            header = ["cluster", "gene_id", "mean_expression", "fraction_expressing"]
            rows = [[r[k] for k in header] for r in data]
            im = ax.scatter(
                [genes.index(r["gene_id"]) for r in data],
                [clusters.index(r["cluster"]) for r in data],
                s=[r["fraction_expressing"] * 180 for r in data],
                c=[r["mean_expression"] for r in data],
                cmap="viridis",
                vmin=0,
            )
            fig.set_size_inches(9, max(3.5, 0.35 * len(clusters) + 1.5))
            ax.set_ylabel("Cluster")
            ax.set_xticks(range(len(genes)), genes, rotation=60, ha="right", fontsize=8)
            ax.set_yticks(range(len(clusters)), clusters)
            fig.colorbar(im, ax=ax, label="Mean log-normalized expression")
            notes.append(
                "Dot area = supplied fraction expressing. Missing cluster/gene records are not plotted and do not mean zero."
            )
            ax.scatter([], [], s=180, c="#64748b", label="100% expressing")
            ax.legend(loc="upper left", bbox_to_anchor=(1.15, 1))
        elif a.kind == "embedding":
            require(
                len(table) <= 5000
                and all(
                    set(["cell_id", "cluster", "UMAP1", "UMAP2"]) <= set(r)
                    for r in table
                ),
                "embedding-table",
                "Use the core adapter embedding table.",
            )
            require(
                len({r["cell_id"] for r in table}) == len(table),
                "duplicate-cell",
                "Cell IDs must be unique.",
            )
            labels = sorted({r["cluster"] for r in table})
            require(len(labels) <= 20, "cluster-limit", "Plot at most 20 clusters.")
            header = ["cell_id", "cluster", "UMAP1", "UMAP2"]
            rows = [
                [r["cell_id"], r["cluster"], float(r["UMAP1"]), float(r["UMAP2"])]
                for r in table
            ]
            require(
                all(math.isfinite(v) for r in rows for v in r[2:]),
                "coordinate",
                "Coordinates must be finite.",
            )
            for label in labels:
                pts = [r for r in rows if r[1] == label]
                ax.scatter(
                    [r[2] for r in pts],
                    [r[3] for r in pts],
                    s=13,
                    alpha=0.8,
                    label=label,
                )
            ax.set_xlabel("UMAP1")
            ax.set_ylabel("UMAP2")
            ax.legend(title="Cluster", loc="upper left", bbox_to_anchor=(1, 1))
            notes.append(
                "Exploratory embedding; visual distances do not establish lineage, cell identity or condition effects."
            )
        else:
            require(
                a.significance in {"pvalue", "padj"}
                and a.alpha is not None
                and a.effect_threshold is not None
                and 0 < a.alpha <= 1
                and a.effect_threshold >= 0
                and math.isfinite(a.effect_threshold),
                "volcano-contract",
                "Declare significance column, alpha and effect threshold.",
                "needs-decision",
            )
            require(
                all({"feature_id", "effect", a.significance} <= set(r) for r in table),
                "result-columns",
                "Map existing results explicitly to feature_id, effect, and the declared significance column.",
            )
            require(
                len({r["feature_id"] for r in table}) == len(table),
                "duplicate-feature",
                "Feature IDs must be unique.",
            )
            header = ["feature_id", "effect", a.significance]
            missing = 0
            for r in table:
                if r["effect"] in {"", "NA"} or r[a.significance] in {"", "NA"}:
                    missing += 1
                    continue
                effect = float(r["effect"])
                pv = float(r[a.significance])
                require(
                    math.isfinite(effect) and math.isfinite(pv) and 0 <= pv <= 1,
                    "result-value",
                    "Use finite effects and p-values in [0,1].",
                )
                rows.append([r["feature_id"], effect, pv])
            require(rows, "plot-empty", "No valid result rows remain.")
            ax.scatter(
                [r[1] for r in rows],
                [-math.log10(max(r[2], 1e-300)) for r in rows],
                c=[
                    (
                        "#b45309"
                        if r[2] <= a.alpha and abs(r[1]) >= a.effect_threshold
                        else "#64748b"
                    )
                    for r in rows
                ],
                s=14,
                alpha=0.7,
            )
            ax.set_xlabel(
                a.effect_label or "Declared effect (confirm direction and scale)"
            )
            ax.set_ylabel("-log10(" + a.significance + ")")
            config.update(
                significance=a.significance,
                alpha=a.alpha,
                effect_threshold=a.effect_threshold,
                effect_label=a.effect_label,
            )
            notes.append(
                f"Explicitly mapped result table; {missing} missing rows excluded from plotting. Zero p-values displayed at 1e-300; source table values retained."
            )
        ax.set_title(title)
        fig.text(0.01, -0.03, "\n".join(notes), fontsize=8, va="top", wrap=True)
        files = {}
        for ext in ["png", "svg"]:
            buffer = io.BytesIO()
            fig.savefig(
                buffer,
                format=ext,
                dpi=160,
                bbox_inches="tight",
                metadata=(
                    {"Date": None} if ext == "svg" else {"Software": "Goose Bio Skills"}
                ),
            )
            files["figure." + ext] = buffer.getvalue()
        plt.close(fig)
        stream = io.StringIO()
        csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(
            [header, *rows]
        )
        files["plot-data.tsv"] = stream.getvalue().encode()
        files["figure.json"] = encoded(
            {
                "schema_version": "1.0",
                "status": "completed",
                "tool": {"name": "goose_result_visualization", "version": VERSION},
                "runtime_versions": {
                    "numpy": np.__version__,
                    "matplotlib": matplotlib.__version__,
                },
                "config": config,
                "input_sha256": {"result": hashlib.sha256(raw).hexdigest()},
                "files": ["figure.png", "figure.svg", "plot-data.tsv"],
                "limitations": notes,
                "network_performed": False,
            }
        )
        new_bundle(a.output, files)
    return {"status": "completed", "kind": a.kind, "version": VERSION}


def main():
    p = argparse.ArgumentParser(
        description="Export a bounded volcano plot, PCA or heatmap with its data and declared settings."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument(
        "--kind",
        choices=[
            "volcano",
            "pca",
            "sample-correlation",
            "heatmap",
            "groups",
            "correlation",
            "concordance",
            "marker-dot",
            "generic-volcano",
            "embedding",
        ],
    )
    for name in ["de-report", "matrix", "counts", "metadata", "output", "title"]:
        p.add_argument("--" + name)
    p.add_argument("--matrix-scale", choices=["log2-normalized", "vst", "rlog"])
    p.add_argument("--significance", choices=["pvalue", "padj"])
    p.add_argument("--alpha", type=float)
    p.add_argument("--effect-threshold", type=float)
    p.add_argument("--top-features", type=int)
    p.add_argument("--feature-scale", choices=["center", "zscore"])
    for name in ["result", "outcome", "x-variable", "y-variable", "effect-label"]:
        p.add_argument("--" + name)
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        report = {
            "status": "completed",
            "method": "DESeq2",
            "model": {
                "results": [
                    {"gene_id": "a", "log2FoldChange": 2, "padj": 0.01},
                    {"gene_id": "b", "log2FoldChange": None, "padj": None},
                ]
            },
        }
        data, missing = volcano_data(report, "padj", 0.05, 1)
        assert data[0][3] == 2 and data[0][4] == "positive" and missing == 1
        report["model"]["results"][0]["padj"] = -1
        try:
            volcano_data(report, "padj", 0.05, 1)
        except UserError:
            pass
        else:
            raise AssertionError("invalid p-value accepted")
        return {
            "status": "pass",
            "version": VERSION,
            "checks": count + 2,
            "scope": "stdlib plot-data/file contracts; rendering smoke is separate",
        }
    if a.kind in {
        "groups",
        "correlation",
        "concordance",
        "marker-dot",
        "generic-volcano",
        "embedding",
    }:
        return expansion_plot(a)
    require(
        a.kind and a.output,
        "missing-plot",
        "Declare a plot kind and new output directory.",
        "needs-decision",
    )
    require(
        not (a.counts and a.matrix),
        "matrix-choice",
        "Use counts with a matching DE report, or a transformed matrix.",
    )
    if a.title:
        require(
            len(a.title) <= 100 and not any(ord(x) < 32 for x in a.title),
            "plot-title",
            "Use a short single-line title.",
        )
    de = None
    hashes = {}
    if a.de_report:
        de, hashes["de_report"] = read_json(a.de_report)
        validate_de(de)
    notes = []
    config = {"kind": a.kind}
    data_rows = []
    header = []
    with tempfile.TemporaryDirectory(
        prefix=".goose-plot-", dir=Path.cwd()
    ) as temporary:
        os.environ["MPLCONFIGDIR"] = temporary
        os.environ["XDG_CACHE_HOME"] = temporary
        try:
            import numpy as np
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise UserError(
                "plot-dependencies",
                "Use a trusted Python environment with NumPy and Matplotlib.",
                "needs-tool",
            ) from exc
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 11,
                "axes.spines.top": False,
                "axes.spines.right": False,
                "axes.labelcolor": "#273444",
                "text.color": "#273444",
                "axes.edgecolor": "#94A3B8",
                "svg.hashsalt": "goose-bio-skills",
                "text.usetex": False,
                "text.parse_math": False,
            }
        )
        fig, ax = plt.subplots(figsize=(9, 6), layout="constrained")
        fig.set_facecolor("white")
        if a.kind == "volcano":
            require(
                de is not None
                and a.significance
                and a.alpha is not None
                and a.effect_threshold is not None,
                "volcano-contract",
                "Provide a DE report, raw/adjusted significance choice, alpha and effect threshold.",
                "needs-decision",
            )
            require(
                not a.matrix and not a.counts,
                "volcano-input",
                "Volcano plots use the result table, not an expression matrix.",
            )
            data_rows, missing = volcano_data(
                de, a.significance, a.alpha, a.effect_threshold
            )
            for category, color, marker in [
                ("other", "#B8C2CC", "."),
                ("negative", "#2563A6", "v"),
                ("positive", "#C27C28", "^"),
            ]:
                group = [r for r in data_rows if r[4] == category]
                if group:
                    ax.scatter(
                        [r[1] for r in group],
                        [r[3] for r in group],
                        s=18 if category == "other" else 26,
                        c=color,
                        marker=marker,
                        alpha=0.72,
                        label=f"{category} (n={len(group)})",
                        linewidths=0,
                    )
            ax.axhline(
                -math.log10(a.alpha), color="#64748B", linestyle="--", linewidth=0.8
            )
            for x in [-a.effect_threshold, a.effect_threshold]:
                ax.axvline(x, color="#94A3B8", linestyle=":", linewidth=0.8)
            contrast = de.get("config", {})
            direction = f"{contrast.get('numerator','numerator')} / {contrast.get('denominator','denominator')}"
            ax.set_xlabel("log2 fold change — " + direction)
            ax.set_ylabel(
                "-log10("
                + ("BH-adjusted p-value" if a.significance == "padj" else "raw p-value")
                + ")"
            )
            ax.set_title(
                a.title or "Differential-expression effect and significance",
                loc="left",
                fontweight="bold",
                pad=24,
            )
            ax.text(
                0,
                1.02,
                f"{len(data_rows):,} features shown · {missing:,} unavailable · threshold {a.alpha:g}, |log2FC| ≥ {a.effect_threshold:g}",
                transform=ax.transAxes,
                fontsize=9,
                color="#64748B",
            )
            ax.legend(frameon=False, fontsize=9)
            header = [
                "gene_id",
                "log2_fold_change",
                a.significance,
                "negative_log10_significance",
                "threshold_group",
            ]
            config.update(
                significance=a.significance,
                alpha=a.alpha,
                effect_threshold=a.effect_threshold,
                contrast=direction,
                unavailable_genes=missing,
                feature_unit=de.get("config", {}).get("feature_unit", "gene"),
            )
            notes = [
                "Null values are omitted and counted; numeric zero p-values are capped at 1e-300 for display only.",
                "Threshold colors describe the declared rule, not biological importance or causality.",
            ]
        else:
            require(
                a.top_features is not None and a.feature_scale,
                "matrix-display-policy",
                "Declare how many variable features to show/use and whether to center or z-score them.",
                "needs-decision",
            )
            genes, samples, values, digest, scale = matrix_data(a, de)
            hashes["matrix_or_counts"] = digest
            require(
                3 <= len(samples) <= 32
                and 2 <= len(genes) <= 30000
                and len(set(genes)) == len(genes)
                and len(set(samples)) == len(samples),
                "matrix-size-or-ids",
                "Use unique IDs, 3–32 samples and 2–30,000 genes.",
            )
            limit = 50 if a.kind == "heatmap" else 2000
            require(
                2 <= a.top_features <= limit,
                "top-features",
                f"Choose 2–{limit} variable features explicitly.",
            )
            array = np.asarray(values, dtype=float)
            variance = np.var(array, axis=1, ddof=1)
            eligible = [i for i, x in enumerate(variance) if x > 0]
            require(
                len(eligible) >= 2,
                "constant-matrix",
                "At least two variable features are required.",
            )
            selected = sorted(eligible, key=lambda i: (-variance[i], genes[i]))[
                : a.top_features
            ]
            x = array[selected, :]
            chosen = [genes[i] for i in selected]
            x = x - x.mean(axis=1, keepdims=True)
            if a.feature_scale == "zscore":
                x = x / x.std(axis=1, ddof=1, keepdims=True)
            config.update(
                input_scale=scale,
                feature_scale=a.feature_scale,
                requested_features=a.top_features,
                selected_features=chosen,
                constant_genes_excluded=len(genes) - len(eligible),
            )
            groups = {sample: "sample" for sample in samples}
            if a.metadata:
                raw = read_local(a.metadata)
                hashes["metadata"] = hashlib.sha256(raw).hexdigest()
                table = tsv(raw)
                require(
                    table[0] == ["sample_id", "group"]
                    and len(table) == len(samples) + 1
                    and len({r[0] for r in table[1:]}) == len(samples)
                    and {r[0] for r in table[1:]} == set(samples),
                    "plot-groups",
                    "Plot metadata requires sample_id/group with exactly the matrix samples.",
                )
                groups = dict(table[1:])
            if a.kind == "sample-correlation":
                # Pearson correlations on the declared transformed features, before per-gene centering.
                uncentered=array[selected,:]
                require(np.all(np.std(uncentered,axis=0,ddof=1)>0), "constant-sample", "Sample correlation is undefined for a constant sample; inspect it without silently dropping it.")
                correlation=np.corrcoef(uncentered,rowvar=False)
                require(np.isfinite(correlation).all(), "undefined-correlation", "Sample correlations must be finite.")
                fig.set_size_inches(max(8,.35*len(samples)+3),max(6,.3*len(samples)+2))
                im=ax.imshow(correlation,cmap="RdBu_r",vmin=-1,vmax=1)
                fig.colorbar(im,ax=ax,label="Pearson r",shrink=.8)
                displayed=[sample+(" ("+groups[sample]+")" if a.metadata else "") for sample in samples]
                ax.set_xticks(range(len(samples)),labels=displayed,rotation=60,ha="right",fontsize=8)
                ax.set_yticks(range(len(samples)),labels=displayed,fontsize=8)
                ax.set_title(a.title or "Sample expression similarity",loc="left",fontweight="bold",pad=20)
                header=["sample_id",*samples]
                data_rows=[[sample,*correlation[i].tolist()] for i,sample in enumerate(samples)]
                config.update(correlation_method="Pearson",feature_scale="not-applied")
                notes=["Pearson similarity uses the selected features on the declared transformed scale, without per-gene centering or z-scoring.","No significance test, sample exclusion, biological identity inference or batch correction is performed."]
            elif a.kind == "pca":
                u, singular, vt = np.linalg.svd(x.T, full_matrices=False)
                require(
                    len(singular) >= 2 and singular[1] > 1e-12,
                    "pca-rank",
                    "The selected matrix has fewer than two varying principal components.",
                )
                scores = u[:, :2] * singular[:2]
                for column in range(2):
                    if vt[column, np.argmax(abs(vt[column]))] < 0:
                        scores[:, column] *= -1
                explained = singular[:2] ** 2 / np.sum(singular**2) * 100
                labels = sorted(set(groups.values()))
                require(
                    len(labels) <= 5,
                    "plot-group-count",
                    "Use at most five displayed groups.",
                )
                colors = ["#2563A6", "#C27C28", "#657B35", "#BD6A8D", "#7C8797"]
                markers = ["o", "s", "^", "D", "v"]
                for i, label in enumerate(labels):
                    positions = [
                        j for j, sample in enumerate(samples) if groups[sample] == label
                    ]
                    ax.scatter(
                        scores[positions, 0],
                        scores[positions, 1],
                        c=colors[i],
                        marker=markers[i],
                        s=64,
                        label=label,
                        edgecolors="white",
                        linewidths=0.8,
                    )
                for i, sample in enumerate(samples):
                    ax.annotate(
                        sample,
                        (scores[i, 0], scores[i, 1]),
                        xytext=(5, 5),
                        textcoords="offset points",
                        fontsize=8,
                    )
                ax.set_xlabel(f"PC1 ({explained[0]:.1f}% variance)")
                ax.set_ylabel(f"PC2 ({explained[1]:.1f}% variance)")
                if a.metadata:
                    ax.legend(frameon=False, title="Declared group")
                ax.set_title(
                    a.title or "Sample PCA", loc="left", fontweight="bold", pad=24
                )
                header = ["sample_id", "PC1", "PC2", "group"]
                data_rows = [
                    [sample, float(scores[i, 0]), float(scores[i, 1]), groups[sample]]
                    for i, sample in enumerate(samples)
                ]
                config["explained_variance_percent"] = explained.tolist()
                notes = [
                    "PCA uses the declared transformed scale and variable-feature selection; no batch correction or hypothesis test is performed.",
                    "Nearby points indicate similarity in the displayed projection, not established biological identity.",
                ]
            else:
                fig.set_size_inches(
                    max(9, 0.32 * len(samples) + 3), max(6, 0.18 * len(chosen) + 1.8)
                )
                extent = max(float(abs(x).max()), 1e-12)
                from matplotlib.colors import LinearSegmentedColormap

                cmap = LinearSegmentedColormap.from_list(
                    "goose_diverging", ["#2563A6", "#F7F8FA", "#C27C28"]
                )
                image = ax.imshow(
                    x,
                    aspect="auto",
                    cmap=cmap,
                    vmin=-extent,
                    vmax=extent,
                    interpolation="nearest",
                )
                fig.colorbar(
                    image,
                    ax=ax,
                    label=(
                        "Within-gene z-score"
                        if a.feature_scale == "zscore"
                        else "Centered transformed value"
                    ),
                    shrink=0.8,
                )
                ax.set_xticks(
                    range(len(samples)), labels=samples, rotation=45, ha="right"
                )
                ax.set_yticks(range(len(chosen)), labels=chosen, fontsize=8)
                ax.set_title(
                    a.title or "Variable-feature expression heatmap",
                    loc="left",
                    fontweight="bold",
                    pad=24,
                )
                header = ["gene_id", *samples]
                data_rows = [[gene, *map(float, row)] for gene, row in zip(chosen, x)]
                notes = [
                    "Genes are ordered by variance with gene-ID tie breaking; samples retain input order. No clustering is implied.",
                    "Color shows the declared within-gene transformation; it is not a significance test.",
                ]
            ax.text(
                0,
                1.02,
                f"{len(samples)} samples · {len(chosen)} variable features · {scale} · {config['feature_scale']}",
                transform=ax.transAxes,
                fontsize=9,
                color="#64748B",
            )
        files = {}
        for extension in ["png", "svg"]:
            buffer = io.BytesIO()
            metadata = (
                {"Date": None}
                if extension == "svg"
                else {"Software": "Goose Bio Skills"}
            )
            fig.savefig(buffer, format=extension, dpi=180, metadata=metadata)
            files["figure." + extension] = buffer.getvalue()
        plt.close(fig)
        stream = io.StringIO()
        csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(
            [header, *data_rows]
        )
        files["plot-data.tsv"] = stream.getvalue().encode()
        report = {
            "schema_version": "1.0",
            "status": "completed",
            "tool": {"name": "goose_result_visualization", "version": VERSION},
            "runtime_versions": {
                "numpy": np.__version__,
                "matplotlib": matplotlib.__version__,
            },
            "config": config,
            "input_sha256": hashes,
            "files": ["figure.png", "figure.svg", "plot-data.tsv"],
            "limitations": notes,
            "network_performed": False,
        }
        files["figure.json"] = encoded(report)
        new_bundle(a.output, files)
    return {
        "status": "completed",
        "kind": a.kind,
        "version": VERSION,
        "files": list(files),
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
