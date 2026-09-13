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


def md(value):
    import html

    text = html.escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    for char in ["\\", "`", "*", "_", "[", "]", "(", ")", "!", "|", "#"]:
        text = text.replace(char, "\\" + char)
    return text


def labeled(items):
    result = []
    seen = set()
    for item in items:
        require(
            "=" in item,
            "labeled-input",
            "Use LABEL=PATH for each report or figure directory.",
        )
        label, path = item.split("=", 1)
        require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}", label) is not None
            and label not in seen,
            "input-label",
            "Use unique simple labels (letters, digits, underscore or hyphen).",
        )
        seen.add(label)
        result.append((label, path))
    return result


def summarize(report):
    require(
        isinstance(report, dict)
        and isinstance(report.get("status"), str)
        and re.fullmatch(r"[a-z][a-z-]{0,40}", report["status"]) is not None,
        "report-status",
        "Each source report must declare a valid status.",
    )
    tool = report.get("tool", {})
    name = tool.get("name", "not-declared") if isinstance(tool, dict) else str(tool)
    if report.get("method") == "DESeq2":
        name = "DESeq2"
    metrics = {}
    if name in {"DESeq2", "goose_microarray_limma"}:
        qc = report.get("model", {}).get("qc", {})
        for key in [
            "genes_input",
            "genes_retained",
            "genes_filtered",
            "pvalue_missing",
            "padj_missing",
        ]:
            value = qc.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                metrics[key] = value
        samples = qc.get("samples")
        if isinstance(samples, list):
            metrics["samples"] = len(samples)
    elif name == "goose_bed3_intervals":
        metrics={k:report['summary'][k] for k in ['a_rows','b_rows','output_rows','output_row_bp_sum','output_coverage_bp']}
    elif name == "check_peak_sets.py" and report.get('analysis') == 'chromatin-peak-set-qc':
        metrics={'peak_sets':len(report['peak_sets']),'checked_interval_rows':sum(x['summary']['interval_count'] for x in report['peak_sets'])}
    elif name == "goose_qpcr":
        metrics={k:report['summary'][k] for k in ['samples','subjects','targets','references','wells']}
    elif name == "goose_independent_2x2":
        metrics={'observations':report['total'],'groups':2}
    elif name == "goose_protein_table_qc":
        metrics = {k: report["summary"][k] for k in ["proteins", "samples", "missing_cells", "zero_cells"]}
    elif name == "protein-level-differential-abundance":
        metrics = {"proteins": len(report["results"]), "samples": report["inputs"]["matrix"]["samples"]}
    elif name == "goose_pcoa":
        metrics = {"samples": len(report["sample_ids"]), "positive_axes": report["positive_axes"], "negative_axes": report["negative_axes"]}
    elif name in {"goose_local_ora", "goose_gseapy_prerank"}:
        rows = report.get("results")
        require(
            isinstance(rows, list),
            "result-table",
            "Enrichment report is missing its result rows.",
        )
        metrics["tested_sets"] = len(rows)
    elif name == "goose_local_id_mapping":
        summary = report.get("summary", {})
        for key in ["input_ids", "one_to_one", "unresolved"]:
            value = summary.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                metrics[key] = value
    elif name in {
        "goose_two_group",
        "goose_correlation",
        "goose_result_concordance",
        "goose_marker_evidence",
        "goose_fastqc_summary",
    }:
        require(
            isinstance(report.get("results"), list),
            "result-table",
            "The declared helper report must contain result rows.",
        )
        metrics["result_rows"] = len(report["results"])
        if isinstance(report.get("excluded"), list):
            metrics["excluded_records"] = len(report["excluded"])
    elif name in {
        "goose_sample_validation",
        "goose_geo_preparation",
        "goose_single_cell_qc",
        "goose_single_cell_core",
        "goose_single_cell_pseudobulk",
    }:
        for key in [
            "samples",
            "features",
            "cells_input",
            "cells_retained",
            "genes",
            "cells",
            "marker_rows",
            "retained_count_total",
        ]:
            value = report.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                metrics[key] = value
        for key in ["unresolved", "excluded", "warnings"]:
            if isinstance(report.get(key), list):
                metrics[key + "_records"] = len(report[key])
    limitations = report.get("limitations", [])
    require(
        isinstance(limitations, list)
        and len(limitations) <= 50
        and all(isinstance(x, str) and len(x) <= 2000 for x in limitations),
        "report-limitations",
        "Limitations must be a bounded string list.",
    )
    return name, metrics, limitations


def main():
    p = argparse.ArgumentParser(
        description="Assemble a readable Markdown report from explicit local result files and figure bundles."
    )
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--reports", nargs="+")
    p.add_argument("--figures", nargs="*", default=[])
    p.add_argument("--note")
    p.add_argument("--output")
    p.add_argument("--title", default="Analysis results")
    p.add_argument("--language", choices=["en", "zh"], default="en")
    a = p.parse_args()
    if a.self_test:
        count = base_checks()
        name, metrics, limits = summarize(
            {
                "status": "partial",
                "tool": {"name": "goose_local_id_mapping"},
                "summary": {"input_ids": 3, "unresolved": 1},
                "limitations": ["unmapped"],
            }
        )
        assert (
            name == "goose_local_id_mapping"
            and metrics["unresolved"] == 1
            and limits == ["unmapped"]
        )
        assert "[x]" not in md("[x](https://example.com)") and "<script>" not in md(
            "<script>"
        )
        try:
            labeled(["a=x", "a=y"])
        except UserError:
            pass
        else:
            raise AssertionError("duplicate label accepted")
        return {"status": "pass", "version": VERSION, "checks": count + 3}
    require(
        a.reports and a.output and 1 <= len(a.reports) <= 20 and len(a.figures) <= 6,
        "report-scope",
        "Specify 1–20 result reports, up to six figure bundles, and a new output directory.",
        "needs-decision",
    )
    require(
        len(a.title) <= 120 and not any(ord(x) < 32 for x in a.title),
        "report-title",
        "Use a short one-line title.",
    )
    if a.note:
        require(
            len(a.note) <= 1000 and not any(ord(x) < 32 for x in a.note),
            "report-note",
            "Use a short one-line study/context note.",
        )
    reports = labeled(a.reports)
    figures = labeled(a.figures)
    zh = a.language == "zh"
    files = {}
    sources = []
    lines = ["# " + md(a.title), ""]
    wording = {
        "intro": (
            "Results from the listed local files. Source analyses were not rerun or reinterpreted.",
            "本报告汇总下列本地文件中的结果；未重新运行分析，也未补充生物学结论。",
        ),
        "summary": ("At a glance", "结果概览"),
        "figures": ("Figures", "图表"),
        "details": ("Recorded settings and limitations", "参数与限制"),
        "partial": (
            "Some source steps are incomplete; this document is not a claim that the whole analysis succeeded.",
            "部分来源步骤未完成；报告生成完成不代表整条分析已经成功。",
        ),
        "complete": (
            "All listed source reports declare completion. Review their assumptions before interpretation.",
            "所列来源报告均声明完成。解释结果前，请核对它们的输入假设。",
        ),
    }
    tr = lambda key: wording[key][int(zh)]
    if a.note:
        lines.extend([("背景说明：" if zh else "Context: ") + md(a.note), ""])
    lines.extend(
        [
            tr("intro"),
            "",
            "## " + tr("summary"),
            "",
            "| "
            + (
                "步骤 | 来源状态 | 内容 |"
                if zh
                else "Step | Source status | Contents |"
            ),
            "| --- | --- | --- |",
        ]
    )
    interpretations = []
    incomplete = False
    total = 0
    metric_names = {
        "genes_input": "输入特征",
        "genes_retained": "保留特征",
        "genes_filtered": "过滤特征",
        "pvalue_missing": "缺失原始 p 值",
        "padj_missing": "缺失校正 p 值",
        "samples": "样本",
        "tested_sets": "检验基因集",
        "input_ids": "输入 ID",
        "one_to_one": "唯一映射",
        "unresolved": "未解决映射",
    }
    for label, path in reports:
        raw = read_local(path)
        total += len(raw)
        require(
            total <= 32 * 1024 * 1024,
            "report-total-size",
            "Source reports exceed 32 MiB.",
        )
        report = parse_json(raw)
        name, metrics, limitations = summarize(report)
        incomplete |= report["status"] != "completed"
        filename = "source-" + label + ".json"
        files[filename] = raw
        summary = (
            "; ".join(
                f"{metric_names.get(k,k) if zh else k}: {v:,}"
                for k, v in metrics.items()
            )
            or name
        )
        lines.append(
            f'| [{md(label)}]({filename}) | {md(report["status"])} | {md(summary)} |'
        )
        if report["status"]=="completed" and name in {"DESeq2","goose_microarray_limma"}:
            cfg=report.get("config",{}); alpha=cfg.get("alpha")
            result_rows=report.get("model",{}).get("results",[])
            if isinstance(alpha,(float,int)) and not isinstance(alpha,bool) and 0<alpha<1:
                significant=[r for r in result_rows if isinstance(r.get("padj"),(float,int)) and not isinstance(r.get("padj"),bool) and math.isfinite(r["padj"]) and 0<=r["padj"]<=alpha and isinstance(r.get("log2FoldChange"),(float,int)) and math.isfinite(r["log2FoldChange"])]
                positive=sum(r["log2FoldChange"]>0 for r in significant);negative=sum(r["log2FoldChange"]<0 for r in significant)
                unit=cfg.get("feature_unit","gene")
                if zh: unit={"probe":"探针","gene":"基因"}.get(unit,unit)
                detail=(f"在 BH 校正阈值 {alpha:g} 下，{len(significant)} 个 {unit} 特征达到阈值；正向 {positive}，负向 {negative}。比较方向为 {cfg.get('numerator')} / {cfg.get('denominator')}。这未附加效应大小筛选；探针数不能直接当作基因数。" if zh else f"At BH threshold {alpha:g}, {len(significant)} {unit} features pass: {positive} positive and {negative} negative for {cfg.get('numerator')} / {cfg.get('denominator')}. No effect-size threshold is applied here; probe counts are not gene counts.")
                interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "goose_bed3_intervals":
            cfg=report['config'];summary=report['summary']
            detail=(f"BED3 {cfg['operation']}，参考声明 {report['reference']['build']}，零基半开、忽略链方向。输出 {summary['output_rows']} 行；逐行长度和 {summary['output_row_bp_sum']} bp，去重覆盖 {summary['output_coverage_bp']} bp。重叠对可重复覆盖同一位置；边界相接不共享碱基，合并不代表生物学共识。" if zh else f"BED3 {cfg['operation']} on declared {report['reference']['build']}; zero-based half-open, strand ignored. Output {summary['output_rows']} rows; row-length sum {summary['output_row_bp_sum']} bp versus union coverage {summary['output_coverage_bp']} bp. Pair multiplicity can double-count; bookended intervals share no bases and merging is not biological consensus.")
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "check_peak_sets.py" and report.get('analysis') == 'chromatin-peak-set-qc':
            detail=('峰集 QC 检查坐标、宽度、重复和去重覆盖；Jaccard 只是碱基覆盖的描述性相似度，不能单独证明重复性、质量或生物学一致。空的区间运算结果应保留为合法空结果，不送入要求非空峰集的 QC 路径。' if zh else 'Peak QC checks coordinates, widths, duplicates and union coverage. Jaccard is descriptive base-coverage similarity, not evidence of reproducibility or quality. Empty algebra results remain valid; the existing peak QC requires nonempty inputs.')
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "goose_qpcr":
            cfg=report['config']
            detail=(f"qPCR 使用 {cfg['method']}，校准组为 {cfg['calibrator_group']}；技术重复只在样本内汇总，生物样本数为 {report['summary']['subjects']}。相对表达只能在同一目标内比较，不能跨 assay 当作绝对表达量；没有组间显著性检验或效率不确定性区间。" if zh else f"qPCR uses {cfg['method']} with calibrator group {cfg['calibrator_group']}. Technical wells are averaged within sample; biological n={report['summary']['subjects']}. Compare within target, not absolute abundance across assays. No group test or efficiency uncertainty interval.")
            if report['status'] != 'completed':
                detail=('该 qPCR 结果仅完成技术 QC；仍有关键事实或孔值未解决，没有生成相对表达量。请先处理报告中的首个待补充事项。' if zh else 'This qPCR result contains technical QC only; unresolved facts or wells prevent relative expression. Resolve the first open item before quantification.')
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "goose_independent_2x2":
            cfg=report['config']
            if report['status']=='completed':
                effect=report['effect'];ci=effect['confidence_interval']
                def number(x):return ('无穷大' if zh else 'infinity') if x=='infinity' else f'{x:.6g}'
                detail=(f"{cfg['numerator']} 相对 {cfg['denominator']}，事件为 {cfg['event_label']}：条件最大似然优势比 {number(effect['estimate'])}，{100*ci['level']:g}% 条件精确区间 [{number(ci['low'])}, {number(ci['high'])}]，双侧 Fisher p={report['test']['pvalue']:.6g}。优势比不是风险比；病例对照抽样的行比例不能解释为总体风险。检验和区间的双侧约定不同，阈值判断不必完全一致。" if zh else f"Event {cfg['event_label']}, {cfg['numerator']} vs {cfg['denominator']}: conditional MLE odds ratio {number(effect['estimate'])}, {100*ci['level']:g}% conditional exact CI [{number(ci['low'])}, {number(ci['high'])}], two-sided Fisher p={report['test']['pvalue']:.6g}. Odds ratio is not risk ratio; case-control row fractions are not population risks. Test and interval use different two-sided conventions.")
            else:
                detail=('该 2×2 表尚未满足独立性、抽样说明或可估计边界；没有生成优势比或检验结论。' if zh else 'This 2x2 table still needs independence, sampling or estimability decisions; no effect or test conclusion was generated.')
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "goose_pcoa":
            detail = (f"PCoA 轴比例使用正特征值之和作分母；负惯量占绝对惯量的 {100*report['negative_inertia_fraction']:.2f}%。未校正距离，分组分离不等于显著差异。" if zh else f"PCoA axes use positive inertia as denominator; negative inertia is {100*report['negative_inertia_fraction']:.2f}% of absolute inertia. Distances are uncorrected; group separation is not a significance test.")
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "goose_protein_table_qc":
            cfg=report['config']
            detail=(f"蛋白定量表：单位 {cfg['unit']}，尺度 {cfg['scale']}，归一化声明 {cfg['normalization_method']}，零值定义 {cfg['zero_semantics']}。模型入口 {'可用' if report['model_ready'] else '需补充决定'}；没有填补、删除或自动归一化。" if zh else f"Protein table: unit {cfg['unit']}, scale {cfg['scale']}, normalization {cfg['normalization_method']}, zero semantics {cfg['zero_semantics']}. Model ready: {report['model_ready']}; no imputation, deletion or normalization.")
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name == "protein-level-differential-abundance":
            cfg=report['config']
            detail=(f"差异丰度单位为蛋白，正效应表示 {cfg['numerator']} 相对 {cfg['denominator']} 的 log2 丰度增加；BH 校正在所有报告蛋白中进行。报告未自行选择显著阈值。" if zh else f"Protein-level effects are log2 abundance differences: {cfg['numerator']} minus {cfg['denominator']}; BH adjustment covers all reported proteins. This report chooses no significance threshold.")
            interpretations.append(f"- [{md(label)}]({filename}): "+md(detail))
        if name in {"goose_local_ora","goose_gseapy_prerank"}:
            detail=("结合背景基因、映射损失、基因集版本及具体贡献基因解释；富集不能单独证明通路激活。" if zh else "Interpret the eligible background, mapping losses, gene-set version and contributing genes; enrichment alone does not establish pathway activation.")
            interpretations.append(f"- [{md(label)}]({filename}): "+detail)
        sources.append(
            {
                "label": label,
                "status": report["status"],
                "tool": name,
                "metrics": metrics,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "config": report.get("config", {}),
                "versions": report.get("runtime_versions", report.get("versions", report.get("model", {}).get("versions", {}))),
                "open_items": {
                    k: report[k]
                    for k in ["unresolved", "excluded", "warnings"]
                    if k in report
                },
                "limitations": limitations,
                "file": filename,
            }
        )
    lines.extend(["", tr("partial" if incomplete else "complete"), ""])
    if interpretations:
        lines.extend(["## "+("如何阅读这些结果" if zh else "Reading these results"),"",*interpretations,""])
    if figures:
        lines.extend(["## " + tr("figures"), ""])
    figure_records = []
    for label, directory in figures:
        folder = local_path(directory)
        require(
            folder.is_dir(),
            "figure-directory",
            "A figure input must be a local exported figure directory.",
        )
        info, info_hash = read_json(folder / "figure.json")
        require(
            isinstance(info, dict)
            and info.get("status") == "completed"
            and info.get("tool", {}).get("name") == "goose_result_visualization",
            "figure-contract",
            "Use completed Goose figure bundles.",
        )
        data = read_local(folder / "figure.png")
        import struct

        require(
            data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 24,
            "figure-type",
            "Only PNG figure assets are embedded.",
        )
        width, height = struct.unpack(">II", data[16:24])
        require(
            1 <= width <= 10000
            and 1 <= height <= 10000
            and width * height <= 25_000_000,
            "figure-size",
            "The figure exceeds display bounds.",
        )
        name = "figure-" + label + ".png"
        files[name] = data
        table = read_local(folder / "plot-data.tsv")
        files["figure-" + label + "-data.tsv"] = table
        files["figure-" + label + ".json"] = encoded(info)
        config = info.get("config", {})
        kind = config.get("kind", "figure")
        lines.extend(
            [
                "### " + md(label),
                "",
                f"![{md(label)}]({name})",
                "",
                ("图表类型：" if zh else "Plot type: ")
                + md(kind)
                + ". "
                + ("[查看绘图数据]" if zh else "[Plot data]")
                + "(figure-"
                + label
                + "-data.tsv)",
                "",
            ]
        )
        for note in info.get("limitations", []):
            lines.extend(["- " + md(note)])
        lines.append("")
        figure_records.append(
            {
                "label": label,
                "metadata_sha256": info_hash,
                "png_sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    lines.extend(["## " + tr("details"), ""])
    for source in sources:
        lines.extend(["### " + md(source["label"]), ""])
        config = source["config"]
        if isinstance(config, dict):
            for key, value in config.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    lines.append("- " + md(key) + ": " + md(value))
        if source["limitations"]:
            lines.append("")
            lines.extend("- " + md(x) for x in source["limitations"])
        lines.extend(["", "SHA-256: `" + source["sha256"] + "`", ""])
    lines.extend(
        [
            "---",
            "",
            (
                "原始 p 值与校正后的显著性不是同一指标；未达到阈值不等于证明没有效应。富集、聚类和图形模式本身不能证明因果关系。"
                if zh
                else "Raw and adjusted significance differ. Missing a threshold is not proof of no effect; enrichment or visual patterns do not establish causality."
            ),
            "",
        ]
    )
    methods = [
        "# " + ("方法与处理记录" if zh else "Methods and processing record"),
        "",
        (
            "从来源文件提取的执行记录；请补充研究设计和实验方法后再用于论文。"
            if zh
            else "Execution facts extracted from source files; add study design and laboratory methods before publication."
        ),
        "",
    ]
    for source in sources:
        methods.extend(
            [
                "## " + md(source["label"]),
                "",
                "["
                + md(source["tool"])
                + "]("
                + source["file"]
                + ") — "
                + md(source["status"]),
                "",
                "```json",
                json.dumps(
                    {
                        "settings": source["config"],
                        "versions": source["versions"],
                        "open_items": source["open_items"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ).replace("`", "\\u0060"),
                "```",
                "",
                "SHA-256: `" + source["sha256"] + "`",
                "",
            ]
        )
    files["methods.md"] = "\n".join(methods).encode("utf-8")
    files["report.md"] = "\n".join(lines).encode("utf-8")
    manifest = {
        "schema_version": "1.0",
        "status": "completed",
        "source_outcome": "partial" if incomplete else "completed",
        "tool": {"name": "goose_qc_report", "version": VERSION},
        "sources": [
            {k: v for k, v in x.items() if k not in {"config", "limitations"}}
            for x in sources
        ],
        "figures": figure_records,
        "files": list(files),
        "limitations": [
            "Document assembly only; source analyses were not rerun or scientifically certified."
        ],
        "network_performed": False,
    }
    files["report.json"] = encoded(manifest)
    new_bundle(a.output, files)
    return {
        "status": "completed",
        "source_outcome": manifest["source_outcome"],
        "reports": len(sources),
        "figures": len(figures),
        "version": VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(cli(main))
