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


VERSION = "0.13.0"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
FACTOR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")


def table_bytes(rows):
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\n").writerows(rows)
    return out.getvalue().encode()


def matrix_table(raw):
    # Blank quantitative cells are inspected as missing, not rejected by the generic TSV reader.
    try:
        rows = list(
            csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("matrix-format", "Use a UTF-8 TSV protein matrix.") from exc
    require(
        2 <= len(rows) <= 10001 and 5 <= len(rows[0]) <= 33,
        "matrix-size",
        "Use 1–10,000 proteins and 4–32 samples.",
    )
    header = rows[0]
    require(
        header[0] == "protein_id" and len(set(header)) == len(header),
        "matrix-header",
        "Start with protein_id followed by unique sample IDs.",
    )
    require(
        all(len(r) == len(header) for r in rows),
        "matrix-shape",
        "Every row must match the header.",
    )
    require(
        all(ID.fullmatch(x) for x in header[1:] + [r[0] for r in rows[1:]])
        and len({r[0] for r in rows[1:]}) == len(rows) - 1,
        "identifiers",
        "Use unique simple protein and sample IDs; identifiers are preserved as text.",
    )
    require(
        all(
            x == x.strip() and len(x) <= 256 and not any(ord(c) < 32 for c in x)
            for r in rows
            for x in r
        ),
        "matrix-cell",
        "Control characters and oversized fields are unsupported.",
    )
    return rows


def full_rank(columns):
    matrix = [list(map(float, r)) for r in zip(*columns)]
    row = 0
    for col in range(len(columns)):
        pivot = next(
            (i for i in range(row, len(matrix)) if abs(matrix[i][col]) > 1e-10), None
        )
        if pivot is None:
            return False
        matrix[row], matrix[pivot] = matrix[pivot], matrix[row]
        scale = matrix[row][col]
        matrix[row] = [v / scale for v in matrix[row]]
        for i in range(row + 1, len(matrix)):
            scale = matrix[i][col]
            matrix[i] = [v - scale * w for v, w in zip(matrix[i], matrix[row])]
        row += 1
    return True


def inspect(matrix_raw, samples_raw, config):
    import statistics

    table = matrix_table(matrix_raw)
    samples = table[0][1:]
    meta = tsv(samples_raw)
    expected = {"sample_id", "condition", "subject_id"} | (
        {"batch"} if config["batch_status"] == "recorded" else set()
    )
    require(
        set(meta[0]) == expected,
        "metadata-columns",
        "Provide sample_id, condition, subject_id and batch only when batch-status is recorded.",
    )
    records = [dict(zip(meta[0], r)) for r in meta[1:]]
    by_id = {r["sample_id"]: r for r in records}
    require(
        len(by_id) == len(records) == len(samples) and set(by_id) == set(samples),
        "sample-join",
        "Metadata must match each matrix sample exactly once.",
    )
    records = [by_id[s] for s in samples]
    require(
        all(
            FACTOR.fullmatch(r["condition"])
            and (config["batch_status"] != "recorded" or FACTOR.fullmatch(r["batch"]))
            for r in records
        ),
        "factor-values",
        "Use explicit letter-led condition/batch labels compatible with the model; never silently rename them.",
    )
    require(
        config["numerator"] != config["denominator"]
        and {r["condition"] for r in records}
        == {config["numerator"], config["denominator"]},
        "contrast",
        "Declare two different condition labels present in the table.",
    )
    unresolved = []

    def block(code, message):
        unresolved.append({"code": code, "question": message})

    if config["feature_level"] != "protein":
        block(
            "feature-level",
            "这是独立 protein 层级的定量表吗？请提供输出层级；peptide 和 protein-group 需要先澄清。",
        )
    if config["scale"] != "log2-normalized" or config["normalization_method"] in {
        "unknown",
        "none",
    }:
        block("scale", "请提供尺度和已有归一化方法；本脚本不会自动归一化或取 log2。")
    if config["unit"] == "unknown":
        block("unit", "请提供定量单位或软件导出定义，以便准确标注图表。")
    if config["zero_semantics"] == "unknown":
        block("zero-semantics", "零表示测量值还是未检出？这会改变缺失统计和模型适用性。")
    if not config["independent"] or len({r["subject_id"] for r in records}) != len(
        samples
    ):
        block("independence", "请确认独立生物对象；同一对象的重复记录不能当作独立重复。")
    if config["batch_status"] == "unknown":
        block("batch-provenance", "请提供批次字段，或明确记录中没有批次变量；不会根据分组推断批次。")
    groups = {
        g: sum(r["condition"] == g for r in records)
        for g in [config["numerator"], config["denominator"]]
    }
    if min(groups.values()) < 2:
        block("replication", "每组至少需要两个独立对象；技术重复不能补足生物重复。")
    if len(table) - 1 < 20:
        block("few-proteins", "此轻量入口至少需要 20 个蛋白；请确认是否提交了预筛选结果。")
    columns = [[int(r["condition"] == g) for r in records] for g in groups]
    batches = []
    if config["batch_status"] == "recorded":
        batches = sorted({r["batch"] for r in records})
        if len(batches) < 2:
            block("constant-batch", "批次列没有变化；请明确选择无批次调整，而不是隐式删除该列。")
        columns += [[int(r["batch"] == b) for r in records] for b in batches[1:]]
    if len(columns) >= len(samples) or not full_rank(columns):
        block("design-confounded", "分组与批次混杂或没有残差自由度；请重新说明可估计的比较，不能用批次校正解决完全混杂。")
    missing_tokens = config["missing_tokens"]
    values = []
    zeros = 0
    for row in table[1:]:
        vals = []
        for cell in row[1:]:
            if cell in missing_tokens:
                vals.append(None)
                continue
            try:
                value = float(cell)
            except ValueError as exc:
                raise UserError(
                    "nonnumeric",
                    "A cell is neither finite numeric nor a declared missing token.",
                ) from exc
            require(
                math.isfinite(value) and abs(value) <= 1e12,
                "numeric-range",
                "Use finite quantified values with absolute magnitude at most 1e12.",
            )
            if value == 0:
                zeros += 1
            vals.append(
                None if value == 0 and config["zero_semantics"] == "missing" else value
            )
        values.append(vals)
    missing = sum(v is None for r in values for v in r)
    if missing:
        block("missing-values", "存在缺失值；请说明处理依据。此完整矩阵路径不会填补、删行或把未检出当作零丰度。")
    summary = []
    for j, s in enumerate(samples):
        measured = sorted(r[j] for r in values if r[j] is not None)
        summary.append(
            {
                "sample_id": s,
                "missing": len(values) - len(measured),
                "missing_fraction": (len(values) - len(measured)) / len(values),
                "observed": len(measured),
                "minimum": min(measured) if measured else None,
                "median": statistics.median(measured) if measured else None,
                "maximum": max(measured) if measured else None,
            }
        )
    result = {
        "schema_version": "1.0",
        "status": "needs-decision" if unresolved else "completed",
        "tool": {"name": "goose_protein_table_qc", "version": VERSION},
        "runtime_versions": {"python": sys.version.split()[0]},
        "config": config,
        "input_sha256": {
            "matrix": hashlib.sha256(matrix_raw).hexdigest(),
            "samples": hashlib.sha256(samples_raw).hexdigest(),
        },
        "summary": {
            "proteins": len(values),
            "samples": len(samples),
            "missing_cells": missing,
            "zero_cells": zeros,
            "groups": groups,
            "batches": batches,
        },
        "sample_qc": summary,
        "protein_qc": [
            {"protein_id": r[0], "missing": sum(v is None for v in vs)}
            for r, vs in zip(table[1:], values)
        ],
        "model_ready": not unresolved,
        "unresolved": unresolved,
        "limitations": [
            "Readiness checks declared facts, not biological validity, statistical power or absence of unmeasured confounding.",
            "No normalization, imputation, row removal, raw MS processing or identification/FDR review. Missingness mechanism is not inferred.",
        ],
    }
    files = {
        "sample-qc.tsv": table_bytes(
            [list(summary[0]), *[list(r.values()) for r in summary]]
        ),
        "protein-qc.tsv": table_bytes(
            [
                ["protein_id", "missing"],
                *[list(r.values()) for r in result["protein_qc"]],
            ]
        ),
    }
    if not unresolved:
        files["model-matrix.tsv"] = matrix_raw
        header = ["sample_id", "condition"] + (["batch"] if batches else [])
        files["model-samples.tsv"] = table_bytes(
            [header, *[[r[k] for k in header] for r in records]]
        )
    result["files"] = list(files)
    result["output_sha256"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items()
    }
    files["qc.json"] = encoded(result)
    return result, files


def main():
    p = argparse.ArgumentParser(
        description="Check protein-level quantified TSVs before the complete normalized-log2 model path."
    )
    p.add_argument("--self-test", action="store_true")
    for n in [
        "matrix",
        "samples",
        "output",
        "unit",
        "normalization-method",
        "numerator",
        "denominator",
    ]:
        p.add_argument("--" + n)
    p.add_argument(
        "--feature-level",
        choices=["protein", "peptide", "protein-group", "unknown"],
        default="unknown",
    )
    p.add_argument(
        "--scale", choices=["log2-normalized", "linear", "unknown"], default="unknown"
    )
    p.add_argument(
        "--zero-semantics", choices=["value", "missing", "unknown"], default="unknown"
    )
    p.add_argument(
        "--batch-status", choices=["absent", "recorded", "unknown"], default="unknown"
    )
    p.add_argument("--missing-token", action="append", default=None)
    p.add_argument("--independent", action="store_true")
    a = p.parse_args()
    if a.self_test:
        rows = matrix_table(b"protein_id\ta\tb\tc\td\n001\t1\t\t2\tNA\n")
        assert rows[1][0] == "001" and rows[1][2] == ""
        assert full_rank([[1, 1, 0, 0], [0, 0, 1, 1]]) and not full_rank(
            [[1, 1], [1, 1]]
        )
        return {"status": "pass", "checks": base_checks() + 3, "version": VERSION}
    require(
        all(
            getattr(a, n)
            for n in [
                "matrix",
                "samples",
                "output",
                "unit",
                "normalization_method",
                "numerator",
                "denominator",
            ]
        ),
        "required-facts",
        "Provide tables, new output, unit, normalization method and contrast.",
        "needs-decision",
    )
    for value in [a.unit, a.normalization_method]:
        require(
            len(value) <= 256 and not any(ord(c) < 32 for c in value),
            "declaration",
            "Use a short plain-text declaration.",
        )
    tokens = a.missing_token if a.missing_token is not None else ["", "NA"]
    require(
        len(tokens) <= 10
        and all(len(t) <= 32 and not any(ord(c) < 32 for c in t) for t in tokens),
        "missing-tokens",
        "Use at most 10 short missing tokens.",
    )
    for t in tokens:
        try:
            v = float(t)
        except ValueError:
            continue
        require(
            not math.isfinite(v),
            "numeric-missing-token",
            "Declare numeric zero via zero-semantics; numeric measurements cannot be missing tokens.",
        )
    cfg = {
        k: getattr(a, k)
        for k in [
            "feature_level",
            "scale",
            "zero_semantics",
            "batch_status",
            "independent",
            "unit",
            "normalization_method",
            "numerator",
            "denominator",
        ]
    }
    cfg["missing_tokens"] = tokens
    result, files = inspect(read_local(a.matrix), read_local(a.samples), cfg)
    new_bundle(a.output, files)
    return {
        "status": result["status"],
        "model_ready": result["model_ready"],
        "first_question": result["unresolved"][0]["question"]
        if result["unresolved"]
        else None,
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
