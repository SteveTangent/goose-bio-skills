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


def concordance(tables, alpha, effect):
    universe = sorted(set().union(*(set(t) for t in tables.values())))
    results = []
    for gene in universe:
        membership = {}
        for label, table in tables.items():
            r = table.get(gene)
            if r is None:
                membership[label] = {"status": "not-present"}
            elif r["tested"] == "false":
                membership[label] = {"status": "not-tested"}
            else:
                membership[label] = {
                    "status": (
                        "selected"
                        if r["padj"] <= alpha and abs(r["effect"]) >= effect
                        else "tested-not-selected"
                    ),
                    "effect": r["effect"],
                    "padj": r["padj"],
                }
        testable = [v for v in membership.values() if "effect" in v]
        common = len(testable) == len(tables)
        direction = (
            (
                "positive"
                if all(v["effect"] > 0 for v in testable)
                else (
                    "negative"
                    if all(v["effect"] < 0 for v in testable)
                    else "mixed-or-zero"
                )
            )
            if common
            else "not-comparable"
        )
        results.append(
            {
                "feature_id": gene,
                "membership": membership,
                "common_tested": common,
                "common_selected": all(
                    v["status"] == "selected" for v in membership.values()
                ),
                "direction": direction,
            }
        )
    pairwise = []
    labels = list(tables)
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            tested = {
                g
                for g in set(tables[a]) & set(tables[b])
                if tables[a][g]["tested"] == "true" and tables[b][g]["tested"] == "true"
            }
            sets = [
                {
                    g
                    for g in tested
                    if tables[label][g]["padj"] <= alpha
                    and abs(tables[label][g]["effect"]) >= effect
                }
                for label in [a, b]
            ]
            union = sets[0] | sets[1]
            pairwise.append(
                {
                    "a": a,
                    "b": b,
                    "common_tested": len(tested),
                    "selected_intersection": len(sets[0] & sets[1]),
                    "selected_union": len(union),
                    "jaccard": len(sets[0] & sets[1]) / len(union) if union else None,
                }
            )
    return results, pairwise


def main():
    p = argparse.ArgumentParser(
        description="Compare 2–5 result tables without conflating absent, untested and nonselected features."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--inputs", nargs="+")
    p.add_argument("--output")
    p.add_argument("--alpha", type=float)
    p.add_argument("--effect-threshold", type=float)
    for n, d in [
        ("id-column", "feature_id"),
        ("effect-column", "effect"),
        ("adjusted-p-column", "padj"),
        ("tested-column", "tested"),
    ]:
        p.add_argument("--" + n, default=d)
    p.add_argument("--reverse", action="append", default=[])
    p.add_argument("--taxon")
    p.add_argument("--namespace")
    p.add_argument("--positive-direction")
    p.add_argument("--effect-scale")
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        t = {
            "A": {"g": {"tested": "true", "effect": 2, "padj": 0.01}},
            "B": {"g": {"tested": "false"}},
        }
        r, _ = concordance(t, 0.05, 1)
        assert (
            not r[0]["common_tested"]
            and r[0]["membership"]["B"]["status"] == "not-tested"
        )
        return {"status": "pass", "version": VERSION, "checks": count + 1}
    require(
        a.inputs
        and 2 <= len(a.inputs) <= 5
        and all([a.output, a.taxon, a.namespace, a.positive_direction, a.effect_scale])
        and a.alpha is not None
        and a.effect_threshold is not None,
        "missing-contract",
        "Declare 2–5 LABEL=FILE inputs, common taxon/namespace/effect scale/direction, thresholds and output.",
        "needs-decision",
    )
    require(
        0 < a.alpha < 1
        and math.isfinite(a.effect_threshold)
        and a.effect_threshold >= 0,
        "thresholds",
        "Use finite explicit thresholds.",
    )
    tables = {}
    hashes = {}
    for item in a.inputs:
        require("=" in item, "input-label", "Use LABEL=FILE.")
        label, path = item.split("=", 1)
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label) and label not in tables,
            "input-label",
            "Use unique simple labels.",
        )
        header, rows, digest = read_table(path)
        fields(
            header, [a.id_column, a.effect_column, a.adjusted_p_column, a.tested_column]
        )
        table = {}
        for r in rows:
            gene = identity(r[a.id_column])
            require(
                gene not in table and r[a.tested_column] in {"true", "false"},
                "identity-or-tested",
                "Unique IDs and explicit true/false tested status required.",
            )
            entry = {"tested": r[a.tested_column]}
            if entry["tested"] == "true":
                entry.update(
                    effect=finite(r[a.effect_column])
                    * (-1 if label in a.reverse else 1),
                    padj=finite(r[a.adjusted_p_column]),
                )
                require(
                    0 <= entry["padj"] <= 1,
                    "adjusted-p",
                    "Adjusted p-values must be in [0,1].",
                )
            table[gene] = entry
        require(
            len(table) <= 30000, "table-size", "Use at most 30,000 rows per comparison."
        )
        tables[label] = table
        hashes[label] = digest
    require(
        set(a.reverse) <= set(tables),
        "reverse-label",
        "Reversed labels must identify supplied comparisons.",
    )
    results, pairs = concordance(tables, a.alpha, a.effect_threshold)
    report = report_base(
        "goose_result_concordance",
        {
            k: v
            for k, v in vars(a).items()
            if k not in {"inputs", "output", "self_test"}
        },
        hashes,
    )
    report.update(results=results, pairwise=pairs, comparisons=list(tables))
    report["limitations"] = [
        "Input tables must already use the declared same taxon, namespace, effect scale and interpretation direction.",
        "Adjusted significance is supplied, not recomputed. Intersections are descriptive, not a meta-analysis or a replication guarantee.",
        "Jaccard uses selected sets within the pairwise common tested universe; empty unions are undefined.",
    ]
    new_file(a.output, encoded(report))
    return {"status": "completed", "features": len(results), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
