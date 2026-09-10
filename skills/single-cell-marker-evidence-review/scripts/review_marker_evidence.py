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


VERSION = "0.11.0"


def main():
    p = argparse.ArgumentParser(
        description="Compare cluster markers with a declared local reference; return candidate evidence, not automatic labels."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--markers")
    p.add_argument("--reference")
    p.add_argument("--output")
    p.add_argument("--taxon")
    p.add_argument("--tissue")
    p.add_argument("--namespace")
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--min-support", type=int, default=2)
    a = p.parse_args()
    if a.self_test:
        return {"status": "pass", "version": VERSION, "checks": base_checks()}
    require(
        all([a.markers, a.reference, a.output, a.taxon, a.tissue, a.namespace]),
        "missing-contract",
        "Provide markers, a local reference, taxon, tissue, namespace and new output.",
        "needs-decision",
    )
    require(
        0 < a.alpha <= 1 and 1 <= a.min_support <= 100,
        "threshold",
        "Use valid adjusted-p and support thresholds.",
    )
    mh, markers, md = read_table(a.markers)
    rh, refs, rd = read_table(a.reference)
    fields(mh, ["cluster", "gene_id", "score", "padj"])
    fields(rh, ["taxon", "tissue", "namespace", "cell_type", "gene_id", "role"])
    require(
        len(markers) <= 20000 and len(refs) <= 5000,
        "record-limit",
        "Use a small marker table and local reference.",
    )
    evidence = {}
    seen = set()
    measures = []
    has_expression = all(c in mh for c in ["mean_expression", "fraction_expressing"])
    for r in markers:
        key = (identity(r["cluster"]), identity(r["gene_id"]))
        require(
            key not in seen, "duplicate-marker", "Use one record per cluster and gene."
        )
        seen.add(key)
        score = finite(r["score"])
        padj = finite(r["padj"])
        require(0 <= padj <= 1, "padj", "Adjusted p-values must lie in [0,1].")
        evidence.setdefault(key[0], set())
        if score > 0 and padj <= a.alpha:
            evidence[key[0]].add(key[1])
        if has_expression:
            mean = finite(r["mean_expression"])
            fraction = finite(r["fraction_expressing"])
            require(
                mean >= 0 and 0 <= fraction <= 1,
                "expression",
                "Use measured nonnegative log-normalized means and fractions in [0,1].",
            )
            measures.append(
                {
                    "cluster": key[0],
                    "gene_id": key[1],
                    "mean_expression": mean,
                    "fraction_expressing": fraction,
                }
            )
    reference = {}
    rseen = set()
    for r in refs:
        require(
            (r["taxon"], r["tissue"], r["namespace"])
            == (a.taxon, a.tissue, a.namespace),
            "reference-context",
            "All reference rows must match the declared taxon, tissue and identifier namespace.",
        )
        key = (identity(r["cell_type"]), identity(r["gene_id"]))
        require(
            key not in rseen and r["role"] in {"support", "conflict"},
            "reference-record",
            "Use one role per candidate and gene: support or conflict.",
        )
        rseen.add(key)
        reference.setdefault(key[0], {"support": set(), "conflict": set()})[
            r["role"]
        ].add(key[1])
    require(
        all(v["support"] for v in reference.values()),
        "reference-support",
        "Every candidate requires at least one supporting marker.",
    )
    results = []
    for cluster, positive in sorted(evidence.items()):
        candidates = []
        for cell_type, ref in sorted(reference.items()):
            support = sorted(positive & ref["support"])
            conflict = sorted(positive & ref["conflict"])
            candidates.append(
                {
                    "cell_type": cell_type,
                    "supporting_markers": support,
                    "conflicting_markers": conflict,
                    "reference_support_count": len(ref["support"]),
                    "support_coverage": len(support) / len(ref["support"]),
                    "meets_minimum_support": len(support) >= a.min_support,
                }
            )
        candidates.sort(
            key=lambda c: (
                -len(c["supporting_markers"]),
                len(c["conflicting_markers"]),
                c["cell_type"],
            )
        )
        plausible = [
            c
            for c in candidates
            if c["meets_minimum_support"] and not c["conflicting_markers"]
        ]
        results.append(
            {
                "cluster": cluster,
                "status": (
                    "candidate-needs-review"
                    if len(plausible) == 1
                    else "ambiguous" if plausible else "unknown"
                ),
                "suggested_candidate": (
                    plausible[0]["cell_type"] if len(plausible) == 1 else None
                ),
                "candidates": candidates,
            }
        )
    report = report_base(
        "goose_marker_evidence",
        {
            "taxon": a.taxon,
            "tissue": a.tissue,
            "namespace": a.namespace,
            "alpha": a.alpha,
            "min_support": a.min_support,
        },
        {"markers": md, "reference": rd},
    )
    report.update(
        status="needs-review", results=results, expression_measurements=measures
    )
    report["limitations"] = [
        "Candidate support is neither a probability nor a validated cell-type assignment. Missing markers in a truncated list are not evidence of absence.",
        "Reference coverage, tissue context and cluster purity require review. Existing cluster labels are never changed. Expression plots use supplied measurements only.",
    ]
    new_file(a.output, encoded(report))
    return {"status": "needs-review", "clusters": len(results), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
