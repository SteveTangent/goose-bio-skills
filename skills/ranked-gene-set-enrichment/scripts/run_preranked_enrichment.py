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


def ranks_from_rows(rows, tie_policy):
    require(
        rows[0] == ["gene_id", "score"],
        "ranking-header",
        "Ranking TSV needs gene_id and score.",
    )
    ranked = []
    for gene, score in rows[1:]:
        try:
            value = float(score)
        except ValueError as exc:
            raise UserError(
                "rank-score", "Ranking scores must be finite numbers."
            ) from exc
        require(math.isfinite(value), "rank-score", "Ranking scores must be finite.")
        ranked.append((gene, value))
    require(
        20 <= len(ranked) <= 30000 and len({r[0] for r in ranked}) == len(ranked),
        "ranking-size-or-duplicates",
        "Use 20–30,000 unique IDs; duplicates require an explicit upstream mapping decision.",
    )
    ties = len(ranked) - len({r[1] for r in ranked})
    require(
        len({r[1] for r in ranked}) > 1,
        "constant-ranking",
        "A constant ranking contains no ordering information.",
    )
    require(
        not ties or tie_policy == "gene-id",
        "tied-ranking",
        "Tied scores need an explicit deterministic tie policy.",
        "needs-decision",
    )
    return sorted(ranked, key=lambda r: (-r[1], r[0])), ties


def main():
    p = argparse.ArgumentParser(
        description="Run bounded offline GSEApy prerank with a complete declared ranking and local gene sets."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--ranking")
    p.add_argument("--handoff")
    for name in [
        "gene-sets",
        "output",
        "taxon",
        "namespace",
        "gene-set-release",
        "ranking-metric",
        "positive-direction",
    ]:
        p.add_argument("--" + name)
    for name in ["min-size", "max-size", "permutations", "seed"]:
        p.add_argument("--" + name, type=int)
    p.add_argument("--tie-policy", choices=["reject", "gene-id"])
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        rows = [["gene_id", "score"]] + [[f"g{i}", str(i)] for i in range(20)]
        ranks, ties = ranks_from_rows(rows, "reject")
        assert ranks[0] == ("g19", 19.0) and ties == 0
        bad = [rows[0]] + [[r[0], "1"] for r in rows[1:]]
        try:
            ranks_from_rows(bad, "gene-id")
        except UserError:
            pass
        else:
            raise AssertionError("constant ranking accepted")
        bad = [r[:] for r in rows]
        bad[2][1] = bad[1][1]
        try:
            ranks_from_rows(bad, "reject")
        except UserError:
            pass
        else:
            raise AssertionError("undeclared ties accepted")
        return {
            "status": "pass",
            "version": VERSION,
            "checks": count + 3,
            "scope": "stdlib ranking and file boundaries; external adapter smoke is separate",
        }
    require(
        all(
            getattr(a, x) is not None
            for x in [
                "gene_sets",
                "output",
                "taxon",
                "namespace",
                "gene_set_release",
                "ranking_metric",
                "positive_direction",
                "min_size",
                "max_size",
                "permutations",
                "seed",
                "tie_policy",
            ]
        ),
        "missing-contract",
        "Declare ranking meaning/direction, identity, local gene sets, size bounds, permutations, seed and tie policy.",
        "needs-decision",
    )
    require(
        bool(a.ranking) != bool(a.handoff),
        "input-choice",
        "Use one ranking TSV or one completed mapping handoff.",
    )
    require(
        100 <= a.permutations <= 10000
        and 0 <= a.seed <= 2**32 - 1
        and 1 <= a.min_size <= a.max_size <= 10000,
        "permutation-or-size",
        "Use 100–10,000 permutations, a uint32 seed and valid gene-set sizes.",
    )
    inputs = {}
    if a.handoff:
        raw = read_local(a.handoff)
        report = parse_json(raw)
        inputs["handoff"] = hashlib.sha256(raw).hexdigest()
        require(
            isinstance(report, dict)
            and report.get("status") == "completed"
            and report.get("config", {}).get("taxon") == a.taxon
            and report.get("config", {}).get("target_namespace") == a.namespace,
            "handoff-identity",
            "Use a completed matching-taxon/namespace ID handoff.",
        )
        payload = report.get("handoff", {})
        require(not payload.get("ranking_metric") or payload["ranking_metric"] == a.ranking_metric, "ranking-metric-mismatch", "Use the signed statistic named by the mapping handoff.")
        require(not payload.get("positive_direction") or payload["positive_direction"] == a.positive_direction, "ranking-direction-mismatch", "Use the numerator named by the mapping handoff.")
        ranking = report.get("handoff", {}).get("ranking")
        require(
            isinstance(ranking, list)
            and all(
                isinstance(x, dict)
                and isinstance(x.get("gene_id"), str)
                and isinstance(x.get("score"), (int, float))
                and not isinstance(x.get("score"), bool)
                for x in ranking
            ),
            "handoff-ranking",
            "Handoff ranking is missing or malformed.",
        )
        rows = [["gene_id", "score"]] + [
            [x["gene_id"], str(x["score"])] for x in ranking
        ]
    else:
        raw = read_local(a.ranking)
        inputs["ranking"] = hashlib.sha256(raw).hexdigest()
        rows = tsv(raw)
    ranked, ties = ranks_from_rows(rows, a.tie_policy)
    genes = {r[0] for r in ranked}
    raw = read_local(a.gene_sets)
    inputs["gene_sets"] = hashlib.sha256(raw).hexdigest()
    table = tsv(raw)
    require(
        table[0] == ["set_id", "gene_id", "taxon", "namespace"],
        "set-header",
        "Gene-set TSV needs set_id, gene_id, taxon, namespace.",
    )
    all_sets = {}
    seen = set()
    for name, gene, species, namespace in table[1:]:
        require(
            species == a.taxon and namespace == a.namespace,
            "gene-set-identity",
            "Gene sets must match the ranking taxon and namespace.",
        )
        require(
            (name, gene) not in seen,
            "duplicate-set-member",
            "Duplicate set members require cleanup.",
        )
        seen.add((name, gene))
        all_sets.setdefault(name, set()).add(gene)
    sets = {
        name: sorted(members & genes)
        for name, members in sorted(all_sets.items())
        if a.min_size <= len(members & genes) <= a.max_size
        and len(members & genes) < len(genes)
    }
    require(
        sets
        and len(sets) <= 500
        and len(ranked) * a.permutations * len(sets) <= 200_000_000,
        "bounded-workload",
        "No testable sets, or the requested job exceeds this small local adapter; reduce the explicitly chosen collection or use another declared adapter.",
        "needs-tool",
    )
    import importlib.metadata

    try:
        version = importlib.metadata.version("gseapy")
        require(
            version == "1.3.0",
            "gseapy-version",
            "This adapter requires GSEApy 1.3.0.",
            "needs-tool",
        )
    except importlib.metadata.PackageNotFoundError as exc:
        raise UserError(
            "missing-gseapy",
            "Install GSEApy 1.3.0 in a separate trusted environment.",
            "needs-tool",
        ) from exc
    with tempfile.TemporaryDirectory(
        prefix=".goose-gsea-", dir=Path.cwd()
    ) as temporary:
        os.environ["MPLCONFIGDIR"] = temporary
        os.environ["XDG_CACHE_HOME"] = temporary
        import pandas as pd
        import gseapy

        # A local dictionary prevents the library from interpreting input as a remote collection name.
        result = gseapy.prerank(
            rnk=pd.DataFrame(ranked),
            gene_sets=sets,
            outdir=None,
            min_size=a.min_size,
            max_size=a.max_size,
            permutation_num=a.permutations,
            seed=a.seed,
            threads=1,
            no_plot=True,
            ascending=None,
            weight=1,
            method="permutation",
            verbose=False,
        )
        output = []
        require(
            set(result.results) == set(sets),
            "result-sets",
            "The external adapter changed the tested set identities.",
            "invalid-output",
        )
        for name, record in sorted(result.results.items()):
            values = {
                key: float(record[key]) for key in ["es", "nes", "pval", "fdr", "fwerp"]
            }
            require(
                all(math.isfinite(x) for x in values.values())
                and all(0 <= values[key] <= 1 for key in ["pval", "fdr", "fwerp"]),
                "result-statistics",
                "The external adapter returned undefined statistics.",
                "invalid-output",
            )
            lead = record.get("lead_genes", "")
            lead = lead.split(";") if isinstance(lead, str) and lead else list(lead)
            require(
                set(lead) <= set(sets[name]),
                "leading-edge",
                "Leading-edge genes differ from the supplied set.",
                "invalid-output",
            )
            output.append(
                {
                    "set_id": name,
                    **values,
                    "leading_edge": lead,
                    "size_in_ranking": len(sets[name]),
                }
            )
    report = {
        "schema_version": "1.0",
        "status": "completed",
        "tool": {"name": "goose_gseapy_prerank", "version": VERSION},
        "runtime_versions": {"gseapy": version, "pandas": pd.__version__},
        "config": {
            x: getattr(a, x)
            for x in [
                "taxon",
                "namespace",
                "gene_set_release",
                "ranking_metric",
                "positive_direction",
                "min_size",
                "max_size",
                "permutations",
                "seed",
                "tie_policy",
            ]
        },
        "input_sha256": inputs,
        "results": output,
        "tied_scores": ties,
        "ranked_genes": len(ranked),
        "excluded_sets": sorted(set(all_sets) - set(sets)),
        "network_performed": False,
        "limitations": [
            "Classic gene-set permutation with weight 1; no phenotype permutation or multilevel procedure.",
            "GSEA empirical FDR is not BH-adjusted significance; very small nominal p-values are limited by the chosen permutations.",
            "Ranking completeness, meaning, taxon and collection suitability are user declarations; enrichment is not proof of pathway activation.",
        ],
    }
    new_file(a.output, encoded(report))
    return {"status": "completed", "tested_sets": len(output), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
