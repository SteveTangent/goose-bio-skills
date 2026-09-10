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


def unique_ids(rows, label):
    require(
        rows[0] == ["gene_id"], "id-header", label + " must have one gene_id column."
    )
    ids = [row[0] for row in rows[1:]]
    require(
        len(ids) == len(set(ids)),
        "duplicate-id",
        label + " has duplicate IDs; resolve them explicitly.",
    )
    return set(ids)


def gene_sets(rows, taxon, namespace):
    require(
        rows[0] == ["set_id", "gene_id", "taxon", "namespace"],
        "set-header",
        "Gene-set TSV needs set_id, gene_id, taxon, namespace.",
    )
    result = {}
    seen = set()
    for set_id, gene_id, species, kind in rows[1:]:
        require(
            species == taxon and kind == namespace,
            "gene-set-identity",
            "Gene-set taxon/namespace differs from the declared inputs.",
        )
        require(
            (set_id, gene_id) not in seen,
            "duplicate-set-member",
            "Duplicate gene-set members are not silently counted twice.",
        )
        seen.add((set_id, gene_id))
        result.setdefault(set_id, set()).add(gene_id)
    require(len(result) <= 2000, "set-count", "Use at most 2,000 local gene sets.")
    return result


def tail_probability(population, successes, draws, observed):
    # Hypergeometric upper tail computed in log space.
    def choose(n, k):
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

    low = max(observed, 0, draws - (population - successes))
    high = min(successes, draws)
    if low > high:
        return 0.0
    terms = [
        choose(successes, k)
        + choose(population - successes, draws - k)
        - choose(population, draws)
        for k in range(low, high + 1)
    ]
    largest = max(terms)
    return min(1.0, math.exp(largest) * math.fsum(math.exp(x - largest) for x in terms))


def adjust_bh(rows):
    order = sorted(range(len(rows)), key=lambda i: rows[i]["pvalue"])
    running = 1.0
    for position in range(len(order) - 1, -1, -1):
        i = order[position]
        running = min(running, rows[i]["pvalue"] * len(order) / (position + 1))
        rows[i]["padj"] = running


def analyze(selected, universe, sets, min_size, max_size):
    require(
        selected <= universe,
        "selected-outside-universe",
        "Selected genes must belong to the measured/tested background.",
    )
    require(
        1 <= len(selected) < len(universe) <= 30000,
        "selection-size",
        "Use a nonempty selected subset and a larger background of at most 30,000 genes.",
    )
    require(
        1 <= min_size <= max_size <= 10000,
        "set-size-policy",
        "Declare valid minimum and maximum overlap sizes.",
    )
    rows = []
    excluded = []
    for name, members in sorted(sets.items()):
        eligible = members & universe
        if not min_size <= len(eligible) <= max_size or len(eligible) == len(universe):
            excluded.append(
                {
                    "set_id": name,
                    "reason": "outside-size-bounds-or-whole-universe",
                    "size_in_universe": len(eligible),
                }
            )
            continue
        hits = selected & eligible
        N, K, n, k = len(universe), len(eligible), len(selected), len(hits)
        rows.append(
            {
                "set_id": name,
                "overlap": k,
                "selected_size": n,
                "set_size_in_universe": K,
                "universe_size": N,
                "fold_enrichment": (k / n) / (K / N),
                "pvalue": tail_probability(N, K, n, k),
                "overlap_gene_ids": sorted(hits),
                "set_members_outside_universe": len(members - universe),
            }
        )
    require(
        rows,
        "no-testable-sets",
        "No gene sets remain under the declared background and size policy.",
    )
    adjust_bh(rows)
    return rows, excluded


def main():
    p = argparse.ArgumentParser(
        description="Run local one-sided hypergeometric ORA with a declared tested universe."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--handoff")
    for arg in [
        "selected",
        "universe",
        "gene-sets",
        "output",
        "taxon",
        "namespace",
        "gene-set-release",
    ]:
        p.add_argument("--" + arg)
    p.add_argument("--min-size", type=int)
    p.add_argument("--max-size", type=int)
    p.add_argument("--alpha", type=float)
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        assert abs(tail_probability(10, 3, 2, 2) - 1 / 15) < 1e-12
        rows, excluded = analyze(
            {"a", "b"}, set("abcdefghij"), {"one": set("abc"), "two": set("def")}, 1, 5
        )
        assert (
            rows[0]["overlap"] == 2
            and abs(rows[0]["padj"] - 2 / 15) < 1e-12
            and not excluded
        )
        try:
            analyze({"z"}, set("abc"), {"one": {"a"}}, 1, 3)
        except UserError:
            pass
        else:
            raise AssertionError("invalid background accepted")
        return {"status": "pass", "version": VERSION, "checks": count + 3}
    require(
        all(
            getattr(a, x) is not None
            for x in [
                "gene_sets",
                "output",
                "taxon",
                "namespace",
                "gene_set_release",
                "min_size",
                "max_size",
                "alpha",
            ]
        ),
        "missing-contract",
        "Declare inputs, identity, collection release, size bounds, alpha and output.",
        "needs-decision",
    )
    require(
        math.isfinite(a.alpha) and 0 < a.alpha < 1,
        "alpha",
        "Alpha must be between 0 and 1.",
    )
    inputs = {"gene_sets": read_local(a.gene_sets)}
    if a.handoff:
        require(
            not a.selected and not a.universe,
            "input-choice",
            "Use either a mapped handoff or separate selected/background files.",
        )
        inputs["handoff"] = read_local(a.handoff)
        handoff = parse_json(inputs["handoff"])
        require(
            isinstance(handoff, dict)
            and handoff.get("status") == "completed"
            and handoff.get("config", {}).get("taxon") == a.taxon
            and handoff.get("config", {}).get("target_namespace") == a.namespace,
            "handoff-identity",
            "Require a completed mapping handoff with matching taxon and target namespace.",
        )
        payload = handoff.get("handoff", {})
        sel = payload.get("selected")
        uni = payload.get("universe")
        require(
            isinstance(sel, list)
            and isinstance(uni, list)
            and all(isinstance(x, str) for x in sel + uni)
            and len(sel) == len(set(sel))
            and len(uni) == len(set(uni)),
            "handoff-sets",
            "Require unique selected and universe IDs.",
        )
        selected, universe = set(sel), set(uni)
    else:
        require(
            a.selected and a.universe,
            "missing-gene-lists",
            "Supply selected and background tables, or a completed mapping handoff.",
            "needs-decision",
        )
        inputs.update(
            {key: read_local(getattr(a, key)) for key in ["selected", "universe"]}
        )
        selected = unique_ids(tsv(inputs["selected"]), "Selected list")
        universe = unique_ids(tsv(inputs["universe"]), "Background")
    sets = gene_sets(tsv(inputs["gene_sets"]), a.taxon, a.namespace)
    rows, excluded = analyze(selected, universe, sets, a.min_size, a.max_size)
    for row in rows:
        row["passes_declared_threshold"] = row["padj"] <= a.alpha
    report = {
        "schema_version": "1.0",
        "status": "completed",
        "tool": {"name": "goose_local_ora", "version": VERSION},
        "method": "one-sided hypergeometric upper tail; BH across all tested sets",
        "config": {
            "taxon": a.taxon,
            "namespace": a.namespace,
            "gene_set_release": a.gene_set_release,
            "alpha": a.alpha,
            "min_size": a.min_size,
            "max_size": a.max_size,
        },
        "input_sha256": {
            key: hashlib.sha256(data).hexdigest() for key, data in inputs.items()
        },
        "results": rows,
        "excluded_sets": excluded,
        "network_performed": False,
        "limitations": [
            "The background and selection policy are user declarations, not inferred from an input list.",
            "Overlapping pathways are dependent; enrichment is not proof of activation or causality.",
            "Genes outside the universe are excluded from each set and counted explicitly; no identifier mapping is performed.",
        ],
    }
    new_file(a.output, encoded(report))
    return {"status": "completed", "tested_sets": len(rows), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
