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
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def table_bytes(rows):
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\n").writerows(rows)
    return out.getvalue().encode()


def read_cq(raw):
    try:
        rows = list(
            csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("cq-format", "Use a UTF-8 TSV Cq table.") from exc
    header = ["sample_id", "assay_id", "run_id", "technical_replicate", "cq", "status"]
    require(
        2 <= len(rows) <= 5001 and rows[0] == header and all(len(r) == 6 for r in rows),
        "cq-shape",
        "Use sample_id, assay_id, run_id, technical_replicate, cq, status; at most 5,000 wells.",
    )
    require(
        all(
            len(v) <= 128 and v == v.strip() and not any(ord(c) < 32 for c in v)
            for r in rows
            for v in r
        ),
        "cq-field",
        "Use short fields without edge whitespace or control characters.",
    )
    records = []
    seen = set()
    for row in rows[1:]:
        record = dict(zip(header, row))
        require(
            all(ID.fullmatch(record[k]) for k in header[:4]),
            "cq-id",
            "Use simple nonempty text IDs.",
        )
        key = tuple(record[k] for k in header[:4])
        require(
            key not in seen,
            "duplicate-well",
            "Repeated sample/assay/run/technical-replicate keys are not allowed.",
        )
        seen.add(key)
        require(
            record["status"] in {"detected", "undetermined", "missing"},
            "cq-status",
            "Map producer status explicitly to detected, undetermined or missing.",
        )
        if record["status"] == "detected":
            try:
                value = float(record["cq"])
            except ValueError as exc:
                raise UserError(
                    "cq-value", "Detected Cq must be finite numeric."
                ) from exc
            require(
                math.isfinite(value) and 0 < value <= 60,
                "cq-value",
                "Detected Cq must lie in (0,60]; assay-specific limits are checked separately.",
            )
            record["value"] = value
        else:
            require(
                record["cq"] == "",
                "censored-value",
                "Undetermined/missing wells must have an empty Cq; never substitute a fixed cycle number.",
            )
            record["value"] = None
        records.append(record)
    return records


def analyze(cq_raw, samples_raw, assays_raw, design):
    import statistics

    required = {
        "assay",
        "method",
        "independent_subjects",
        "assay_qc_reviewed",
        "assay_qc_note",
        "reference_rationale",
        "calibrator_group",
        "max_technical_cq_range",
    }
    require(
        isinstance(design, dict) and set(design) == required,
        "design-schema",
        "Provide assay, method, independent_subjects, assay_qc_reviewed, assay_qc_note, reference_rationale, calibrator_group and max_technical_cq_range.",
    )
    require(
        isinstance(design["assay"], str)
        and isinstance(design["method"], str)
        and design["method"] in {"delta-delta-cq", "efficiency-corrected", "unknown"}
        and type(design["independent_subjects"]) is bool
        and type(design["assay_qc_reviewed"]) is bool,
        "design-values",
        "Use supported methods and explicit boolean declarations.",
    )
    for k in ["assay_qc_note", "reference_rationale", "calibrator_group"]:
        require(
            isinstance(design[k], str)
            and design[k] == design[k].strip()
            and 0 < len(design[k]) <= 500
            and not any(ord(c) < 32 for c in design[k]),
            "design-note",
            "Keep declarations explicit; use unknown for unresolved facts.",
        )
    threshold = design["max_technical_cq_range"]
    require(
        type(threshold) in {int, float}
        and math.isfinite(threshold)
        and 0 < threshold <= 5,
        "replicate-threshold",
        "Declare a positive technical Cq range limit at most 5 cycles; this is a user policy, not a universal acceptance cutoff.",
    )
    samples = tsv(samples_raw)
    assays = tsv(assays_raw)
    wells = read_cq(cq_raw)
    require(
        samples[0] == ["sample_id", "subject_id", "group"]
        and 4 <= len(samples) - 1 <= 32,
        "sample-schema",
        "Use sample_id/subject_id/group for 4–32 samples.",
    )
    sample_records = [dict(zip(samples[0], r)) for r in samples[1:]]
    by_sample = {r["sample_id"]: r for r in sample_records}
    require(
        len(by_sample) == len(sample_records)
        and all(ID.fullmatch(r[k]) for r in sample_records for k in samples[0]),
        "sample-identities",
        "Sample IDs must be unique simple text; subject and group labels must be nonempty.",
    )
    require(
        assays[0]
        == [
            "assay_id",
            "role",
            "amplification_factor",
            "cq_min",
            "cq_max",
            "validation_note",
        ]
        and 2 <= len(assays) - 1 <= 11,
        "assay-schema",
        "Use assay_id/role/amplification_factor/cq_min/cq_max/validation_note for 2–11 assays.",
    )
    assay_records = [dict(zip(assays[0], r)) for r in assays[1:]]
    by_assay = {r["assay_id"]: r for r in assay_records}
    require(
        len(by_assay) == len(assay_records)
        and all(
            ID.fullmatch(r["assay_id"]) and r["role"] in {"target", "reference"}
            for r in assay_records
        ),
        "assay-identities",
        "Assays need unique IDs and target/reference roles.",
    )
    require(
        all(
            r["validation_note"] == r["validation_note"].strip()
            and r["validation_note"].strip()
            for r in assay_records
        ),
        "assay-note",
        "Provide nonblank validation notes without edge whitespace; use unknown for unresolved evidence.",
    )
    refs = [r["assay_id"] for r in assay_records if r["role"] == "reference"]
    targets = [r["assay_id"] for r in assay_records if r["role"] == "target"]
    require(
        1 <= len(refs) <= 3 and 1 <= len(targets) <= 8,
        "reference-and-targets",
        "Provide 1–3 justified reference assays and 1–8 target assays.",
        "needs-decision",
    )
    require(
        all(r["sample_id"] in by_sample and r["assay_id"] in by_assay for r in wells),
        "well-join",
        "Every well must match the declared sample and assay tables.",
    )
    unresolved = []

    def block(code, question):
        if not any(x["code"] == code for x in unresolved):
            unresolved.append({"code": code, "question": question})

    if design["assay"] != "RT-qPCR":
        block("assay-type", "这些 Cq 是否来自 RNA 逆转录后的 RT-qPCR？DNA 拷贝数与转录表达的解释不同，请先明确实验类型。")
    if len({r["run_id"] for r in wells}) != 1:
        block("multiple-runs", "检测到多个运行批次；请先说明跨板校准方法。这条轻量路径只处理一次共同校准的运行。")
    if not design["independent_subjects"] or len(
        {r["subject_id"] for r in sample_records}
    ) != len(sample_records):
        block("independence", "哪个字段对应独立生物对象？同一对象多次取样或技术重复不能直接增加生物样本数。")
    if not design["assay_qc_reviewed"] or design["assay_qc_note"].lower() == "unknown":
        block("assay-qc", "请补充特异性、阴性/无 RT 对照及定量范围的检查结论；Cq 表本身不能证明这些检查通过。")
    if design["reference_rationale"].lower() == "unknown":
        block("reference-rationale", "这些内参在本实验条件下为何适合归一化？请提供选择依据，不默认某个基因始终稳定。")
    if design["method"] == "unknown":
        block("method", "请根据实测扩增效率选择计算方法；效率不同建议用 efficiency-corrected，不默认套用 2^-ΔΔCq。")
    groups = {
        g: sum(r["group"] == g for r in sample_records)
        for g in sorted({r["group"] for r in sample_records})
    }
    if not 2 <= len(groups) <= 4 or min(groups.values()) < 2:
        block("group-replication", "请提供 2–4 组、每组至少两个独立生物对象；此路径不对技术重复做组间推断。")
    if design["calibrator_group"] not in groups:
        block("calibrator", "哪一组作为校准组？相对表达的 1 倍基准取该组独立对象归一化量的几何均值。")
    for assay in assay_records:
        for key in ["amplification_factor", "cq_min", "cq_max"]:
            try:
                value = float(assay[key])
            except ValueError:
                require(
                    assay[key] == "unknown",
                    "assay-number",
                    "Assay numbers must be finite numeric or explicit unknown.",
                )
                value = None
            require(
                value is None or math.isfinite(value),
                "assay-number",
                "Assay numerical declarations must be finite.",
            )
            assay[key] = value
        factor = assay["amplification_factor"]
        lo, hi = assay["cq_min"], assay["cq_max"]
        if (
            factor is None
            or lo is None
            or hi is None
            or assay["validation_note"].lower() == "unknown"
        ):
            block(
                "assay-validation",
                "请提供各 assay 的扩增因子、有效 Cq 范围与验证记录；扩增因子 1.9 表示约 90% 效率，而非 1.9%。",
            )
        if factor is not None:
            require(
                1 < factor <= 2.2,
                "amplification-factor",
                "Use a validated per-cycle amplification factor in (1,2.2], not a percent. This cap is an adapter boundary.",
            )
        if lo is not None and hi is not None:
            require(
                0 < lo < hi <= 60,
                "assay-range",
                "Assay-specific quantitative Cq limits must satisfy 0 < min < max <= 60.",
            )
        if design["method"] == "delta-delta-cq" and factor != 2.0:
            block(
                "doubling-assumption",
                "2^-ΔΔCq 需要各目标和内参均有按 2 倍扩增计算的验证依据；当前因子不满足。建议选择效率校正方法。",
            )
    cells = {(sample, assay): [] for sample in by_sample for assay in by_assay}
    for well in wells:
        cells[(well["sample_id"], well["assay_id"])].append(well)
    qc = []
    means = {}
    for (sample, assay), replicates in cells.items():
        values = [r["value"] for r in replicates if r["value"] is not None]
        record = by_assay[assay]
        if not 2 <= len(replicates) <= 4:
            block("replicate-count", "每个样本/assay 是否都有 2–4 个技术重复？请补齐缺失记录，不把未提供的孔当作未检出。")
        if len(values) != len(replicates):
            block(
                "unquantified-wells", "存在未检出或缺失孔；请根据检测限和实验记录决定处理方式，本路径不会填入固定 Cq 或自动删除。"
            )
        span = max(values) - min(values) if values else None
        if span is not None and span > threshold:
            block(
                "replicate-disagreement",
                "有技术重复超过声明的 Cq 差异阈值；请检查原始扩增曲线/实验记录，不自动挑选最接近的两个孔。",
            )
        if (
            record["cq_min"] is not None
            and record["cq_max"] is not None
            and any(not record["cq_min"] <= v <= record["cq_max"] for v in values)
        ):
            block(
                "outside-quantitative-range",
                "有检测值超出声明的定量范围；检测到信号不等于可以可靠定量，请补充检测限/定量范围依据。",
            )
        mean = statistics.mean(values) if values else None
        if mean is not None:
            means[(sample, assay)] = mean
        qc.append(
            {
                "sample_id": sample,
                "assay_id": assay,
                "wells": len(replicates),
                "detected": len(values),
                "undetermined": sum(r["status"] == "undetermined" for r in replicates),
                "missing": sum(r["status"] == "missing" for r in replicates),
                "mean_cq_observed": mean,
                "sd_cq_observed": statistics.stdev(values) if len(values) > 1 else None,
                "cq_range_observed": span,
            }
        )
    result = {
        "schema_version": "1.0",
        "status": "needs-decision" if unresolved else "completed",
        "tool": {"name": "goose_qpcr", "version": VERSION},
        "runtime_versions": {"python": sys.version.split()[0]},
        "config": design,
        "summary": {
            "samples": len(sample_records),
            "subjects": len({r["subject_id"] for r in sample_records}),
            "targets": len(targets),
            "references": len(refs),
            "wells": len(wells),
        },
        "assays": assay_records,
        "sample_metadata": sample_records,
        "run_ids": sorted({r["run_id"] for r in wells}),
        "technical_qc": qc,
        "unresolved": unresolved,
        "results": [],
        "group_summary": [],
        "limitations": [
            "Relative expression is within each target versus the declared calibrator group, not absolute copy number or expression comparable across different assays.",
            "Technical wells are averaged within sample/assay; group n counts independent subjects, not wells. No outlier removal, missing-value substitution or automatic reference selection.",
            "Amplification factors, reference stability, assay specificity and controls are supplied declarations, not verified from amplification curves.",
            "Efficiency/calibrator uncertainty and prediction intervals are not propagated; no significance tests or MIQE-compliance claim.",
            "One run and independent subjects only; no cross-run calibration, repeated-measure modeling or clinical use.",
        ],
    }
    files = {
        "technical-qc.tsv": table_bytes([list(qc[0]), *[list(x.values()) for x in qc]])
    }
    if not unresolved:
        log_quantity = {}
        for sample in by_sample:
            reference_mean = statistics.mean(
                -means[(sample, ref)] * math.log2(by_assay[ref]["amplification_factor"])
                for ref in refs
            )
            for target in targets:
                log_quantity[(sample, target)] = (
                    -means[(sample, target)]
                    * math.log2(by_assay[target]["amplification_factor"])
                    - reference_mean
                )
        calibrators = {
            t: statistics.mean(
                log_quantity[(s, t)]
                for s in by_sample
                if by_sample[s]["group"] == design["calibrator_group"]
            )
            for t in targets
        }
        for sample, metadata in by_sample.items():
            for target in targets:
                logrel = log_quantity[(sample, target)] - calibrators[target]
                result["results"].append(
                    {
                        "sample_id": sample,
                        "subject_id": metadata["subject_id"],
                        "group": metadata["group"],
                        "target": target,
                        "log2_relative_expression": logrel,
                        "relative_expression": 2**logrel,
                    }
                )
        for target in targets:
            for group, n in groups.items():
                values = [
                    x["log2_relative_expression"]
                    for x in result["results"]
                    if x["target"] == target and x["group"] == group
                ]
                mean = statistics.mean(values)
                result["group_summary"].append(
                    {
                        "target": target,
                        "group": group,
                        "n_subjects": n,
                        "mean_log2_relative_expression": mean,
                        "geometric_mean_relative_expression": 2**mean,
                        "sd_log2_relative_expression": statistics.stdev(values),
                    }
                )
        result["calibrator_log2_normalized_quantities"] = calibrators
        for name, key in [
            ("relative-expression.tsv", "results"),
            ("group-summary.tsv", "group_summary"),
        ]:
            files[name] = table_bytes(
                [list(result[key][0]), *[list(x.values()) for x in result[key]]]
            )
    return result, files


def main():
    p = argparse.ArgumentParser(
        description="Check one-run qPCR Cq tables and compute declared-efficiency relative expression."
    )
    p.add_argument("--self-test", action="store_true")
    for name in ["cq", "samples", "assays", "design", "output"]:
        p.add_argument("--" + name)
    a = p.parse_args()
    if a.self_test:
        records = read_cq(
            b"sample_id\tassay_id\trun_id\ttechnical_replicate\tcq\tstatus\n001\tT\trun1\t01\t\tundetermined\n"
        )
        assert records[0]["value"] is None and records[0]["sample_id"] == "001"
        try:
            read_cq(
                b"sample_id\tassay_id\trun_id\ttechnical_replicate\tcq\tstatus\n001\tT\trun1\t01\t40\tundetermined\n"
            )
        except UserError:
            pass
        else:
            raise AssertionError("fixed cycle substitution accepted")
        return {"status": "pass", "checks": base_checks() + 2, "version": VERSION}
    require(
        all(getattr(a, n) for n in ["cq", "samples", "assays", "design", "output"]),
        "required-inputs",
        "Provide Cq, sample, assay and design files and a new output directory.",
        "needs-decision",
    )
    raw = {k: read_local(getattr(a, k)) for k in ["cq", "samples", "assays", "design"]}
    result, files = analyze(
        raw["cq"], raw["samples"], raw["assays"], parse_json(raw["design"])
    )
    result["input_sha256"] = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
    result["files"] = list(files)
    result["output_sha256"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items()
    }
    files["qpcr.json"] = encoded(result)
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
