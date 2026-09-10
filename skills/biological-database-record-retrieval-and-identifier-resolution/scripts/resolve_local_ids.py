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


VERSION = "0.10.0"


def resolve_ids(ids, rows, taxon, strip_versions):
    require(
        rows[0] == ["source_id", "target_id", "taxon"],
        "mapping-header",
        "Local mapping TSV needs source_id, target_id, taxon.",
    )
    lookup = {}
    seen = set()
    for source, target, species in rows[1:]:
        require(
            species == taxon,
            "taxon-mismatch",
            "The local mapping table contains a different taxon; do not guess the organism.",
        )
        require(
            (source, target) not in seen,
            "duplicate-mapping-row",
            "Remove exact duplicate mapping rows explicitly.",
        )
        seen.add((source, target))
        lookup.setdefault(source, set()).add(target)
    result = []
    for source in ids:
        normalized = source
        if strip_versions:
            require(
                re.fullmatch(r"ENS[A-Z]*G[0-9]+(?:\.[0-9]+)?", source) is not None,
                "version-strip-scope",
                "Version stripping is limited to declared Ensembl gene IDs.",
            )
            normalized = source.split(".")[0]
        targets = sorted(lookup.get(normalized, set()))
        result.append(
            {
                "source_id": source,
                "lookup_id": normalized,
                "target_ids": targets,
                "status": "unmapped"
                if not targets
                else "mapped"
                if len(targets) == 1
                else "ambiguous",
            }
        )
    inverse = {}
    for row in result:
        if row["status"] == "mapped":
            inverse.setdefault(row["target_ids"][0], []).append(row["source_id"])
    collisions = {
        target: sources for target, sources in inverse.items() if len(sources) > 1
    }
    for row in result:
        if row["status"] == "mapped" and row["target_ids"][0] in collisions:
            row["status"] = "many-to-one"
    return result, collisions


def main():
    p = argparse.ArgumentParser(
        description="Resolve a bounded gene-ID list with an explicit local mapping table; preserve ambiguity."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--ids")
    p.add_argument("--de-report")
    p.add_argument("--mapping")
    p.add_argument("--output")
    for name in ["taxon", "source-namespace", "target-namespace", "mapping-release"]:
        p.add_argument("--" + name)
    p.add_argument("--strip-source-version", action="store_true")
    p.add_argument("--unresolved-policy", choices=["preserve", "exclude"])
    p.add_argument("--alpha", type=float)
    p.add_argument("--effect-threshold", type=float)
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        rows = [
            ["source_id", "target_id", "taxon"],
            ["a", "A", "9606"],
            ["b", "B", "9606"],
            ["b", "C", "9606"],
            ["c", "A", "9606"],
        ]
        result, collisions = resolve_ids(["a", "b", "c", "d"], rows, "9606", False)
        assert [x["status"] for x in result] == [
            "many-to-one",
            "ambiguous",
            "many-to-one",
            "unmapped",
        ] and collisions == {"A": ["a", "c"]}
        try:
            resolve_ids(["a"], rows, "10090", False)
        except UserError:
            pass
        else:
            raise AssertionError("wrong species accepted")
        result, _ = resolve_ids(
            ["ENSG000001.2"],
            [["source_id", "target_id", "taxon"], ["ENSG000001", "A", "9606"]],
            "9606",
            True,
        )
        assert result[0]["lookup_id"] == "ENSG000001"
        return {"status": "pass", "version": VERSION, "checks": count + 3}
    require(
        bool(a.ids) != bool(a.de_report),
        "input-choice",
        "Supply one ID table or one completed DE report.",
    )
    require(
        all(
            [
                a.mapping,
                a.output,
                a.taxon,
                a.source_namespace,
                a.target_namespace,
                a.mapping_release,
                a.unresolved_policy,
            ]
        ),
        "missing-contract",
        "Declare taxon, both namespaces, mapping release and unresolved-ID policy.",
        "needs-decision",
    )
    mapping_data = read_local(a.mapping)
    rows = tsv(mapping_data)
    de = None
    if a.de_report:
        de, digest = read_json(a.de_report)
        require(
            isinstance(de, dict)
            and de.get("status") == "completed"
            and de.get("method") == "DESeq2",
            "de-contract",
            "Use a completed bounded Goose DESeq2 report.",
        )
        model = de.get("model", {})
        source_rows = model.get("results")
        require(
            isinstance(source_rows, list)
            and source_rows
            and all(
                isinstance(x, dict) and isinstance(x.get("gene_id"), str)
                for x in source_rows
            ),
            "de-results",
            "DE results require gene_id rows.",
        )
        ids = [r["gene_id"] for r in source_rows]
        require(
            a.alpha is not None
            and a.effect_threshold is not None
            and math.isfinite(a.alpha)
            and 0 < a.alpha < 1
            and math.isfinite(a.effect_threshold)
            and a.effect_threshold >= 0,
            "selection-policy",
            "For DE handoff declare adjusted-p alpha and absolute log2-fold-change threshold.",
            "needs-decision",
        )
    else:
        raw = read_local(a.ids)
        digest = hashlib.sha256(raw).hexdigest()
        table = tsv(raw)
        require(
            table[0] == ["gene_id"],
            "id-header",
            "ID table must have one gene_id column.",
        )
        ids = [r[0] for r in table[1:]]
    require(
        1 <= len(ids) <= 30000 and len(set(ids)) == len(ids),
        "id-count-or-duplicates",
        "Use 1–30,000 unique source IDs.",
    )
    resolved, collisions = resolve_ids(ids, rows, a.taxon, a.strip_source_version)
    unresolved = [r for r in resolved if r["status"] != "mapped"]
    report = {
        "schema_version": "1.0",
        "status": "partial"
        if unresolved and a.unresolved_policy == "preserve"
        else "completed",
        "tool": {"name": "goose_local_id_mapping", "version": VERSION},
        "config": {
            "taxon": a.taxon,
            "source_namespace": a.source_namespace,
            "target_namespace": a.target_namespace,
            "mapping_release": a.mapping_release,
            "strip_source_version": a.strip_source_version,
            "unresolved_policy": a.unresolved_policy,
        },
        "input_sha256": {
            "source": digest,
            "mapping": hashlib.sha256(mapping_data).hexdigest(),
        },
        "mapping": resolved,
        "many_to_one": collisions,
        "summary": {
            "input_ids": len(ids),
            "one_to_one": len(ids) - len(unresolved),
            "unresolved": len(unresolved),
        },
        "network_performed": False,
        "limitations": [
            "Local mapping source, release, namespaces and organism are declarations that require review.",
            "No automatic choice among aliases, many-to-one or one-to-many mappings; unresolved rows remain explicit.",
        ],
    }
    if de is not None and report["status"] == "completed":
        translation = {
            r["source_id"]: r["target_ids"][0]
            for r in resolved
            if r["status"] == "mapped"
        }
        universe = []
        selected = []
        ranking = []
        excluded = []
        ranking_excluded = []
        for row in source_rows:
            values = [row.get(k) for k in ["pvalue", "padj", "stat", "log2FoldChange"]]
            require(
                all(
                    v is None
                    or (
                        isinstance(v, (int, float))
                        and not isinstance(v, bool)
                        and math.isfinite(v)
                    )
                    for v in values
                ),
                "de-numeric",
                "DE handoff contains non-finite statistics.",
            )
            for value in values[:2]:
                require(
                    value is None or 0 <= value <= 1,
                    "de-pvalue",
                    "DE significance must be null or between 0 and 1.",
                )
            target = translation.get(row["gene_id"])
            if target is not None and row.get("stat") is not None:
                ranking.append({"gene_id": target, "score": row["stat"]})
            else:
                ranking_excluded.append(row["gene_id"])
            if target is None or any(v is None for v in values):
                excluded.append(row["gene_id"])
                continue
            universe.append(target)
            if (
                row["padj"] <= a.alpha
                and abs(row["log2FoldChange"]) >= a.effect_threshold
            ):
                selected.append(target)
        require(
            len(set(universe)) == len(universe),
            "target-collision",
            "Target identifiers are not unique.",
        )
        report["handoff"] = {
            "universe": sorted(universe),
            "selected": sorted(selected),
            "ranking": sorted(ranking, key=lambda x: (-x["score"], x["gene_id"])),
            "excluded_source_ids": excluded,
            "ranking_excluded_source_ids": ranking_excluded,
            "universe_definition": "One-to-one mapped genes with finite pvalue, padj, stat and log2FoldChange in the completed DE report. This is eligibility for this declared selection, not all measured genes.",
            "ranking_definition": "All one-to-one mapped finite Wald statistics, including genes without adjusted p-values; positive toward the numerator. Only listed unavailable statistics and unresolved mappings are excluded.",
            "alpha": a.alpha,
            "absolute_log2fc_threshold": a.effect_threshold,
        }
    new_file(a.output, encoded(report))
    return {
        "status": report["status"],
        "mapped": len(ids) - len(unresolved),
        "unresolved": len(unresolved),
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
