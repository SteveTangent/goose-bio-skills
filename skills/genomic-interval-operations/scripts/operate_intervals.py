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


VERSION = "0.15.0"
MAX_ROWS = 2000
MAX_PAIRS = 20000
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def table_bytes(rows):
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\n").writerows(rows)
    return out.getvalue().encode("ascii")


def rows(raw, columns, limit):
    require(
        all(x >= 32 or x in {9, 10, 13} for x in raw),
        "table-control",
        "Control separators other than tab/newline are not accepted.",
    )
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise UserError(
            "encoding", "Use exact ASCII tab-separated BED3 or contig sizes."
        ) from exc
    require(
        len(lines) <= limit, "row-limit", f"Use at most {limit} rows.", "needs-tool"
    )
    parsed = [line.split("\t") for line in lines]
    require(
        all(
            len(r) == columns
            and all(
                0 < len(v) <= 128 and v == v.strip() and not any(ord(c) < 32 for c in v)
                for v in r
            )
            for r in parsed
        ),
        "table-format",
        "Use exact nonblank tab-separated rows, without headers, comments, track lines or extra columns.",
    )
    return parsed


def contigs_input(raw):
    records = rows(raw, 2, 10000)
    require(records, "empty-contigs", "Provide a nonempty contig-size dictionary.")
    require(
        all(
            TOKEN.fullmatch(r[0])
            and INTEGER.fullmatch(r[1])
            and 0 < int(r[1]) <= 2147483647
            for r in records
        ),
        "contig-values",
        "Use exact contig tokens and positive integer lengths at most 2^31-1.",
    )
    require(
        len({r[0] for r in records}) == len(records),
        "duplicate-contig",
        "Contig names must be unique; no aliasing is performed.",
    )
    return {r[0]: int(r[1]) for r in records}


def bed_input(raw, contigs, duplicates):
    records = []
    for index, row in enumerate(rows(raw, 3, MAX_ROWS), 1):
        chrom, start, end = row
        require(
            chrom in contigs,
            "unknown-contig",
            "Every interval must use an exact contig in the declared dictionary; chr1 and 1 are not aliases.",
        )
        require(
            INTEGER.fullmatch(start) and INTEGER.fullmatch(end),
            "coordinate-integer",
            "BED coordinates must be nonnegative decimal integers.",
        )
        start, end = int(start), int(end)
        require(
            0 <= start < end <= contigs[chrom],
            "coordinate-range",
            "Use positive-width zero-based half-open intervals within the declared contig length.",
        )
        records.append(dict(row=index, chrom=chrom, start=start, end=end))
    ndup = len(records) - len({(r["chrom"], r["start"], r["end"]) for r in records})
    require(
        duplicates != "reject" or ndup == 0,
        "duplicate-interval",
        "Duplicate coordinates found. Confirm whether they represent separate records; preserve explicitly or correct upstream.",
    )
    return records, ndup


def merge_records(records, order, bookended):
    result, trace = [], []
    for row in sorted(
        records, key=lambda r: (order[r["chrom"]], r["start"], r["end"], r["row"])
    ):
        touches = (
            result
            and row["chrom"] == result[-1]["chrom"]
            and (
                row["start"] <= result[-1]["end"]
                if bookended
                else row["start"] < result[-1]["end"]
            )
        )
        if touches:
            result[-1]["end"] = max(result[-1]["end"], row["end"])
        else:
            result.append(dict(chrom=row["chrom"], start=row["start"], end=row["end"]))
        trace.append(dict(output_row=len(result), a_row=row["row"]))
    return result, trace


def coverage(records, order):
    normalized = [dict(r, row=i) for i, r in enumerate(records)]
    return sum(r["end"] - r["start"] for r in merge_records(normalized, order, True)[0])


def analyze(a_raw, b_raw, contigs_raw, config):
    keys = {
        "operation",
        "build_a",
        "build_b",
        "contig_build",
        "coordinate_system",
        "strand_policy",
        "duplicates",
        "adjacency",
    }
    require(
        isinstance(config, dict) and set(config) == keys,
        "config-schema",
        "Provide the exact operation, reference, coordinate, strand, duplicate and adjacency declarations.",
    )
    require(
        config["operation"] in {"merge", "intersect"}
        and config["duplicates"] in {"preserve", "reject"},
        "operation-policy",
        "Choose merge/intersect and preserve/reject duplicates explicitly.",
    )
    require(
        config["coordinate_system"] == "bed0-half-open",
        "coordinate-convention",
        "此路径只接 BED 零基半开坐标：[10,20) 包含 10 个碱基。请核对生成工具的坐标说明，不自动转换。",
        "needs-decision",
    )
    require(
        config["strand_policy"] == "ignore",
        "strand-policy",
        "BED3 不包含链方向。是否可以忽略链方向？如果研究问题依赖正负链，请使用另一条明确的 BED6 路径。",
        "needs-decision",
    )
    builds = [config["build_a"], config["contig_build"]]
    if config["operation"] == "intersect":
        require(
            b_raw is not None and config["adjacency"] is None,
            "intersect-input",
            "Intersection requires B and has no merge-adjacency option.",
        )
        builds.append(config["build_b"])
    else:
        require(
            b_raw is None
            and config["build_b"] is None
            and config["adjacency"] in {"overlap-only", "bookended"},
            "merge-input",
            "Merge one A table; explicitly choose overlap-only or bookended, without B.",
        )
    require(
        all(
            isinstance(x, str)
            and TOKEN.fullmatch(x)
            and x.lower() not in {"unknown", "na", "none"}
            for x in builds
        ),
        "build-declaration",
        "请提供每个输入及 contig 表的准确参考版本；不能从染色体名字或坐标猜测。",
        "needs-decision",
    )
    require(
        len(set(builds)) == 1,
        "build-mismatch",
        "输入参考版本不一致。请提供同版本数据；此路径不做 liftover，也不把 hg38/GRCh38 自动当成同一声明。",
        "needs-decision",
    )
    contigs = contigs_input(contigs_raw)
    order = {name: i for i, name in enumerate(contigs)}
    a, adup = bed_input(a_raw, contigs, config["duplicates"])
    b, bdup = (
        bed_input(b_raw, contigs, config["duplicates"])
        if b_raw is not None
        else ([], 0)
    )
    if config["operation"] == "merge":
        results, trace = merge_records(a, order, config["adjacency"] == "bookended")
    else:
        hits = []
        by_chrom = {
            chrom: sorted(
                [r for r in b if r["chrom"] == chrom],
                key=lambda r: (r["start"], r["end"], r["row"]),
            )
            for chrom in contigs
        }
        for left in a:
            for right in by_chrom[left["chrom"]]:
                if right["start"] >= left["end"]:
                    break
                start, end = max(left["start"], right["start"]), min(
                    left["end"], right["end"]
                )
                if start < end:
                    require(
                        len(hits) < MAX_PAIRS,
                        "pair-limit",
                        "More than 20,000 overlap pairs; use a declared larger-scale tool. No partial output is published.",
                        "needs-tool",
                    )
                    hits.append((left["chrom"], start, end, left["row"], right["row"]))
        hits.sort(key=lambda r: (order[r[0]], *r[1:]))
        results = [dict(chrom=r[0], start=r[1], end=r[2]) for r in hits]
        trace = [
            dict(output_row=i, a_row=r[3], b_row=r[4], overlap_bp=r[2] - r[1])
            for i, r in enumerate(hits, 1)
        ]
    summary = dict(
        a_rows=len(a),
        b_rows=len(b),
        a_duplicate_rows=adup,
        b_duplicate_rows=bdup,
        output_rows=len(results),
        a_coverage_bp=coverage(a, order),
        b_coverage_bp=coverage(b, order),
        output_coverage_bp=coverage(results, order),
        output_row_bp_sum=sum(r["end"] - r["start"] for r in results),
    )
    record = dict(
        schema_version="1.0",
        status="completed",
        tool=dict(name="goose_bed3_intervals", version=VERSION),
        runtime_versions={"python": sys.version.split()[0]},
        config=config,
        reference=dict(
            build=builds[0],
            identity_status="caller-declared-not-independently-verified",
            contigs=contigs,
            contig_order=list(contigs),
        ),
        inputs=dict(a=a, b=b),
        results=results,
        trace=trace,
        summary=summary,
        limitations=[
            "Reference identity is caller-declared; coordinates and contig lengths cannot independently prove assembly identity.",
            "Exact BED3 only; strand is ignored by explicit declaration. No aliasing, liftover, coordinate conversion, nearest-gene assignment or biological consensus inference.",
            "Intersection retains one clipped interval per positive-overlap pair, including multiplicity. Row-length sums can double-count bases; output_coverage_bp is the union length.",
            "Merge collapses coordinates, including duplicates, while trace retains source row membership. Bookended intervals meet at a boundary but share zero bases.",
            "Empty results are valid, not evidence of missing biological association. Output order follows the contig dictionary, then coordinate and input row.",
            "At most 2,000 rows per BED and 20,000 overlap pairs; whole-genome performance and Agent/scientific benchmarks are unverified.",
        ],
    )
    headers = (
        ["output_row", "a_row"]
        if config["operation"] == "merge"
        else ["output_row", "a_row", "b_row", "overlap_bp"]
    )
    files = {
        "result.bed": table_bytes(
            [[r["chrom"], r["start"], r["end"]] for r in results]
        ),
        "trace.tsv": table_bytes([headers, *[[r[k] for k in headers] for r in trace]]),
    }
    record["input_sha256"] = {
        "a": hashlib.sha256(a_raw).hexdigest(),
        "contigs": hashlib.sha256(contigs_raw).hexdigest(),
    }
    if b_raw is not None:
        record["input_sha256"]["b"] = hashlib.sha256(b_raw).hexdigest()
    record["files"] = list(files)
    record["output_sha256"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items()
    }
    return record, files


def main():
    p = argparse.ArgumentParser(
        description="Bounded same-build BED3 interval merge or positive-overlap intersection."
    )
    p.add_argument("--self-test", action="store_true")
    for key in [
        "a",
        "b",
        "contigs",
        "build-a",
        "build-b",
        "contig-build",
        "coordinate-system",
        "strand-policy",
        "output",
    ]:
        p.add_argument("--" + key)
    p.add_argument("--operation", choices=["merge", "intersect"])
    p.add_argument("--duplicates", choices=["preserve", "reject"])
    p.add_argument("--adjacency", choices=["overlap-only", "bookended"])
    args = p.parse_args()
    if args.self_test:
        order = {"chr1": 0}
        data = [
            dict(row=1, chrom="chr1", start=0, end=5),
            dict(row=2, chrom="chr1", start=5, end=10),
        ]
        assert (
            len(merge_records(data, order, False)[0]) == 2
            and len(merge_records(data, order, True)[0]) == 1
        )
        assert coverage(data, order) == 10
        return dict(status="pass", checks=base_checks() + 2, version=VERSION)
    require(
        all(
            getattr(args, k)
            for k in ["a", "contigs", "output", "operation", "duplicates"]
        ),
        "required-inputs",
        "Provide BED A, contigs, operation, duplicate policy and a new output directory; declare builds, coordinate and strand semantics.",
        "needs-decision",
    )
    config = {
        k: getattr(args, k)
        for k in [
            "operation",
            "build_a",
            "build_b",
            "contig_build",
            "coordinate_system",
            "strand_policy",
            "duplicates",
            "adjacency",
        ]
    }
    result, files = analyze(
        read_local(args.a),
        read_local(args.b) if args.b else None,
        read_local(args.contigs),
        config,
    )
    files["intervals.json"] = encoded(result)
    new_bundle(args.output, files)
    return dict(
        status="completed",
        operation=args.operation,
        summary=result["summary"],
        version=VERSION,
    )


if __name__ == "__main__":
    raise SystemExit(cli(main))
