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


def group_rows(rows, a):
    grouped = {}
    seen = set()
    removed = []
    sample_design = {}
    for r in rows:
        sample = identity(r[a.sample_column])
        group = r[a.group_column]
        outcome = identity(r[a.outcome_column])
        require(
            group in {a.numerator, a.denominator},
            "group-level",
            "Use exactly the two declared group levels.",
        )
        require(
            (sample, outcome) not in seen,
            "duplicate-sample",
            "Duplicate sample/outcome records must be resolved.",
        )
        seen.add((sample, outcome))
        subject = identity(r[a.subject_column]) if a.subject_column else sample
        require(
            sample not in sample_design or sample_design[sample] == (group, subject),
            "inconsistent-sample-design",
            "A sample has inconsistent group or subject records across outcomes.",
        )
        sample_design[sample] = (group, subject)
        record = {
            "sample_id": sample,
            "subject_id": subject,
            "group": group,
            "value": None,
        }
        if r[a.value_column] in {"", "NA"}:
            require(
                a.missing_policy == "complete",
                "missing-values",
                "Missing values require an explicit complete-case policy.",
                "needs-decision",
            )
            removed.append(
                {"sample_id": sample, "outcome": outcome, "reason": "missing-value"}
            )
        else:
            record["value"] = finite(r[a.value_column])
        grouped.setdefault(outcome, []).append(record)
    require(
        1 <= len(grouped) <= 20,
        "outcome-count",
        "Use 1–20 continuous outcomes; do not pass genome-wide raw counts.",
    )
    return grouped, removed


def main():
    p = argparse.ArgumentParser(
        description="One declared independent or paired two-group continuous-outcome comparison."
    )
    p.add_argument("--self-test", action="store_true")
    for n in ["input", "output", "numerator", "denominator", "unit"]:
        p.add_argument("--" + n)
    for n, d in [
        ("sample-column", "sample_id"),
        ("group-column", "group"),
        ("outcome-column", "outcome"),
        ("value-column", "value"),
    ]:
        p.add_argument("--" + n, default=d)
    p.add_argument("--subject-column")
    p.add_argument("--method", choices=["welch", "paired"])
    p.add_argument("--missing-policy", choices=["error", "complete"])
    p.add_argument("--scale", choices=["continuous", "log2-normalized"])
    p.add_argument("--confidence", type=float)
    p.add_argument("--independent-units-declared", action="store_true")
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        assert finite("2.5") == 2.5
        try:
            finite("inf")
        except UserError:
            pass
        else:
            raise AssertionError("nonfinite accepted")
        return {"status": "pass", "version": VERSION, "checks": count + 2}
    require(
        all(
            getattr(a, n) is not None
            for n in [
                "input",
                "output",
                "numerator",
                "denominator",
                "unit",
                "method",
                "missing_policy",
                "scale",
                "confidence",
            ]
        )
        and a.independent_units_declared,
        "missing-contract",
        "Declare continuous scale/units, groups, design, independent units, confidence and missing policy.",
        "needs-decision",
    )
    require(
        a.numerator != a.denominator and 0 < a.confidence < 1,
        "contrast",
        "Use distinct groups and confidence between zero and one.",
    )
    require(
        a.method != "paired" or a.subject_column,
        "pairing",
        "Paired analysis needs a subject column.",
        "needs-decision",
    )
    header, rows, digest = read_table(a.input)
    fields(
        header,
        [a.sample_column, a.group_column, a.outcome_column, a.value_column]
        + ([a.subject_column] if a.subject_column else []),
    )
    grouped, removed = group_rows(rows, a)
    try:
        import numpy as np
        import scipy
        from scipy import stats
    except ImportError as exc:
        raise UserError(
            "dependencies", "Use a trusted NumPy/SciPy environment.", "needs-tool"
        ) from exc
    results = []
    points = []
    for outcome, records in sorted(grouped.items()):
        subjects = {}
        for r in records:
            key = (r["subject_id"], r["group"])
            require(
                key not in subjects,
                "replicate-unit",
                "Multiple records for the same independent unit/group require upstream aggregation.",
            )
            subjects[key] = r
        x = {s: r for (s, g), r in subjects.items() if g == a.numerator}
        y = {s: r for (s, g), r in subjects.items() if g == a.denominator}
        if a.method == "paired":
            incomplete = {
                s
                for s in set(x) | set(y)
                if s not in x
                or s not in y
                or x[s]["value"] is None
                or y[s]["value"] is None
            }
            require(
                not incomplete or a.missing_policy == "complete",
                "incomplete-pairs",
                "Pairs are incomplete; supply matching subjects or declare complete-case exclusion.",
                "needs-decision",
            )
            for s in sorted(incomplete):
                removed.append(
                    {"subject_id": s, "outcome": outcome, "reason": "incomplete-pair"}
                )
            units = sorted((set(x) & set(y)) - incomplete)
            xr = [x[s] for s in units]
            yr = [y[s] for s in units]
        else:
            require(
                not (set(x) & set(y)),
                "dependent-units",
                "Independent groups share subject IDs; choose the correct design.",
            )
            xr = [r for _, r in sorted(x.items()) if r["value"] is not None]
            yr = [r for _, r in sorted(y.items()) if r["value"] is not None]
        xv = np.asarray([r["value"] for r in xr])
        yv = np.asarray([r["value"] for r in yr])
        require(
            len(xv) >= 2 and len(yv) >= 2,
            "replication",
            "At least two available independent units per group/pair are required; this is a computational minimum, not adequate power.",
        )
        fit = (
            stats.ttest_rel(xv, yv)
            if a.method == "paired"
            else stats.ttest_ind(xv, yv, equal_var=False)
        )
        ci = fit.confidence_interval(a.confidence)
        numbers = [fit.statistic, fit.pvalue, fit.df, ci.low, ci.high]
        require(
            all(math.isfinite(float(v)) for v in numbers),
            "undefined-inference",
            "Zero variability or degenerate data leave inference undefined.",
            "invalid-output",
        )
        results.append(
            {
                "outcome": outcome,
                "numerator_n": len(xv),
                "denominator_n": len(yv),
                "numerator_mean": float(xv.mean()),
                "denominator_mean": float(yv.mean()),
                "mean_difference": float(xv.mean() - yv.mean()),
                "ci_low": float(ci.low),
                "ci_high": float(ci.high),
                "statistic": float(fit.statistic),
                "df": float(fit.df),
                "pvalue": float(fit.pvalue),
            }
        )
        points.extend({"outcome": outcome, **r} for r in xr + yr)
    report = report_base(
        "goose_two_group", vars(a) | {"input": None, "output": None}, {"table": digest}
    )
    report["config"] = {
        k: v
        for k, v in report["config"].items()
        if k not in {"input", "output", "self_test"}
    }
    report.update(
        results=results,
        points=points,
        excluded=removed,
        runtime_versions={"numpy": np.__version__, "scipy": scipy.__version__},
    )
    report["limitations"] = [
        "Continuous-outcome two-sided t inference under the declared independent/paired design; no covariate or repeated-measure model.",
        "No multiplicity correction was performed. Send complete declared hypothesis families to the existing correction Skill.",
        "Mean differences and intervals are in the declared analysis scale; nonsignificance is not proof of no effect.",
    ]
    new_file(a.output, encoded(report))
    return {"status": "completed", "outcomes": len(results), "version": VERSION}


if __name__ == "__main__":
    raise SystemExit(cli(main))
