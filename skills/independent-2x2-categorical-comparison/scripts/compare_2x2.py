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


VERSION = "0.14.0"
EXPECTED_SCIPY = "1.17.1"


def counts_input(raw, numerator, denominator):
    rows = tsv(raw)
    require(
        rows[0] == ["group", "event", "non_event"] and len(rows) == 3,
        "table-schema",
        "Use exactly two rows with group/event/non_event integer counts.",
    )
    require(
        numerator != denominator
        and {r[0] for r in rows[1:]} == {numerator, denominator},
        "group-direction",
        "Choose two distinct group labels present exactly once.",
    )
    require(
        all(re.fullmatch(r"0|[1-9][0-9]{0,5}", x) for r in rows[1:] for x in r[1:]),
        "integer-counts",
        "Counts must be nonnegative integers; proportions, weights, missing values and fractions are unsupported.",
    )
    by_group = {r[0]: list(map(int, r[1:])) for r in rows[1:]}
    table = [by_group[numerator], by_group[denominator]]
    require(
        0 < sum(map(sum, table)) <= 100000,
        "table-size",
        "Use 1–100,000 total independent observations.",
    )
    return table


def json_number(value):
    value = float(value)
    require(
        not math.isnan(value) and value >= 0,
        "undefined-estimate",
        "An estimate is undefined; check table margins.",
        "needs-decision",
    )
    return "infinity" if math.isinf(value) else value


def estimate(table, confidence):
    try:
        import scipy
        from scipy.stats import fisher_exact
        from scipy.stats.contingency import odds_ratio
    except ImportError as exc:
        raise UserError(
            "scipy-required", "Use the trusted SciPy 1.17.1 environment.", "needs-tool"
        ) from exc
    require(
        scipy.__version__ == EXPECTED_SCIPY,
        "scipy-version",
        "This preview supports SciPy 1.17.1; other versions are unverified.",
        "needs-tool",
    )
    fisher = fisher_exact(table, alternative="two-sided")
    odds = odds_ratio(table, kind="conditional")
    interval = odds.confidence_interval(
        confidence_level=confidence, alternative="two-sided"
    )
    pvalue = float(fisher.pvalue)
    require(
        math.isfinite(pvalue) and 0 <= pvalue <= 1,
        "test-result",
        "Fisher test returned an invalid probability.",
        "needs-tool",
    )
    return {
        "test": {
            "method": "Fisher exact, two-sided probability ordering",
            "alternative": "two-sided",
            "null_odds_ratio": 1,
            "pvalue": pvalue,
            "multiplicity_adjustment": "none; one prespecified table",
        },
        "effect": {
            "measure": "odds-ratio",
            "estimate_method": "conditional maximum likelihood",
            "estimate": json_number(odds.statistic),
            "confidence_interval": {
                "level": confidence,
                "method": "conditional exact equal-tailed",
                "low": json_number(interval.low),
                "high": json_number(interval.high),
            },
        },
        "sample_odds_ratio": json_number(fisher.statistic),
        "runtime_versions": {
            "scipy": scipy.__version__,
            "python": sys.version.split()[0],
        },
    }


def analyze(raw, config):
    table = counts_input(raw, config["numerator"], config["denominator"])
    unresolved = []
    if not config["independent"]:
        unresolved.append(
            {
                "code": "independence",
                "question": "这些计数是否来自独立对象？配对、重复观察或加权人数需要另一种方法，不能按独立 2×2 表分析。",
            }
        )
    if config["sampling_design"] == "unknown":
        unresolved.append(
            {
                "code": "sampling-design",
                "question": "这是队列、随机分组、横断面还是病例对照抽样？抽样方式决定分母能否解释为总体风险。",
            }
        )
    if (
        min([*map(sum, table), table[0][0] + table[1][0], table[0][1] + table[1][1]])
        == 0
    ):
        unresolved.append(
            {
                "code": "zero-margin",
                "question": "有整行或整列为零，优势比不可估计；请核对组别与事件定义，不能自动加 0.5。",
            }
        )
    result = {
        "schema_version": "1.0",
        "status": "needs-decision" if unresolved else "completed",
        "tool": {"name": "goose_independent_2x2", "version": VERSION},
        "config": config,
        "input_sha256": {"table": hashlib.sha256(raw).hexdigest()},
        "table": table,
        "row_labels": [config["numerator"], config["denominator"]],
        "column_labels": [config["event_label"], config["nonevent_label"]],
        "total": sum(map(sum, table)),
        "group_counts": [
            {"group": label, "event": r[0], "non_event": r[1], "sample_total": sum(r)}
            for label, r in zip([config["numerator"], config["denominator"]], table)
        ],
        "unresolved": unresolved,
        "runtime_versions": {"python": sys.version.split()[0]},
        "limitations": [
            "Odds ratio compares event odds in numerator versus denominator; it is not a risk ratio or causal effect.",
            "Case-control sampling does not identify population risks from row fractions; this helper never estimates population risk or risk difference.",
            "The two-sided Fisher p-value uses probability ordering; the equal-tailed exact confidence interval uses a different inversion convention and need not cross its threshold at the same point.",
            "Conditional MLE and exact conditional interval are distinct from the sample cross-product odds ratio. Zero and infinity are retained without continuity correction.",
            "One prespecified table only; no paired observations, repeated subjects, weighted counts, strata, regression, multiplicity across many tables or clinical recommendation.",
        ],
    }
    if not unresolved:
        result.update(estimate(table, config["confidence_level"]))
    return result


def main():
    p = argparse.ArgumentParser(
        description="One independent 2x2 table: Fisher test and conditional odds ratio with exact interval."
    )
    p.add_argument("--self-test", action="store_true")
    for name in [
        "table",
        "output",
        "numerator",
        "denominator",
        "event-label",
        "nonevent-label",
    ]:
        p.add_argument("--" + name)
    p.add_argument("--independent", action="store_true")
    p.add_argument(
        "--sampling-design",
        choices=["cohort", "randomized", "cross-sectional", "case-control", "unknown"],
        default="unknown",
    )
    p.add_argument("--confidence-level", type=float, default=0.95)
    a = p.parse_args()
    if a.self_test:
        assert counts_input(
            b"group\tevent\tnon_event\nA\t0\t10\nB\t5\t5\n", "A", "B"
        ) == [[0, 10], [5, 5]]
        assert json_number(float("inf")) == "infinity" and json_number(0) == 0
        return {
            "status": "pass",
            "checks": base_checks() + 2,
            "version": VERSION,
            "scope": "dependency-free schema/I/O checks; numerical execution checked separately",
        }
    require(
        all(
            getattr(a, k)
            for k in [
                "table",
                "output",
                "numerator",
                "denominator",
                "event_label",
                "nonevent_label",
            ]
        ),
        "required-facts",
        "Provide a table, new output, group direction and event/non-event meaning.",
        "needs-decision",
    )
    require(
        math.isfinite(a.confidence_level) and 0.8 <= a.confidence_level <= 0.999,
        "confidence-level",
        "Choose a confidence level from 0.8 to 0.999.",
    )
    for k in ["numerator", "denominator", "event_label", "nonevent_label"]:
        value = getattr(a, k)
        require(
            value == value.strip()
            and len(value) <= 128
            and not any(ord(c) < 32 for c in value),
            "labels",
            "Use short explicit labels without edge whitespace.",
        )
    require(
        a.event_label != a.nonevent_label,
        "outcome-labels",
        "Event and non-event meanings must differ.",
    )
    config = {
        k: getattr(a, k)
        for k in [
            "numerator",
            "denominator",
            "event_label",
            "nonevent_label",
            "independent",
            "sampling_design",
            "confidence_level",
        ]
    }
    result = analyze(read_local(a.table), config)
    stream = io.StringIO()
    csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(
        [
            ["group", "event", "non_event", "sample_total"],
            *[list(r.values()) for r in result["group_counts"]],
        ]
    )
    files = {"counts.tsv": stream.getvalue().encode()}
    result["files"] = list(files)
    result["output_sha256"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items()
    }
    files["comparison.json"] = encoded(result)
    new_bundle(a.output, files)
    return {
        "status": result["status"],
        "first_question": result["unresolved"][0]["question"]
        if result["unresolved"]
        else None,
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
