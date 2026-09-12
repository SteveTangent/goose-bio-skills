#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Track local analysis facts and checked handoffs; never execute an analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.4.0"
MAX_FILE = 16 * 1024 * 1024
TOOLS = {
    "qpcr-relative-expression-and-qc": "goose_qpcr",
    "independent-2x2-categorical-comparison": "goose_independent_2x2",
    "proteomics-quantification-table-qc": "goose_protein_table_qc",
    "protein-level-differential-abundance": "protein-level-differential-abundance",
    "distance-matrix-principal-coordinates-analysis": "goose_pcoa",
    "count-based-differential-expression": "goose_deseq2",
    "normalized-microarray-differential-expression": "goose_microarray_limma",
    "biological-database-record-retrieval-and-identifier-resolution": "goose_local_id_mapping",
    "over-representation-analysis": "goose_local_ora",
    "ranked-gene-set-enrichment": "goose_gseapy_prerank",
    "bioinformatics-format-and-identifier-validation": "goose_sample_validation",
    "bioinformatics-qc-and-publication-reporting": "goose_qc_report",
    "two-group-comparison-and-effect-estimation": "goose_two_group",
    "public-expression-dataset-preparation": "goose_geo_preparation",
    "single-cell-object-io-and-qc": "goose_single_cell_qc",
    "single-cell-core-analysis": "goose_single_cell_core",
    "single-cell-marker-evidence-review": "goose_marker_evidence",
    "single-cell-pseudobulk-aggregation": "goose_single_cell_pseudobulk",
    "bioinformatics-result-visualization": "goose_result_visualization",
}
OUTCOMES = {
    "completed",
    "partial",
    "needs-decision",
    "needs-review",
    "needs-tool",
    "invalid-input",
    "invalid-output",
    "blocked-or-failed",
}
QUESTIONS = {
    "taxon": "这些数据属于哪个物种？请提供物种名或 TaxID。",
    "assay": "这是哪类实验？请说明测量方式，以便选择适用的方法。",
    "scale": "矩阵里的数值是什么尺度？请提供生成步骤或软件输出说明。",
    "biological_unit": "哪个字段代表独立生物学样本？技术重复或单个细胞不能自动当作独立样本。",
    "numerator": "本次比较哪一组作为分子（效应为正时增加的组）？",
    "denominator": "哪一组作为参照组？请提供样本表中的原始组名。",
    "platform": "这个表达矩阵对应哪个平台？请提供明确的 GPL 编号。",
}


class WorkflowError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise WorkflowError(message)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def no_links(path):
    for part in [path, *path.parents]:
        require(not part.is_symlink(), "Symbolic links are not accepted.")


def relative(value):
    require(
        isinstance(value, str) and 0 < len(value) <= 240,
        "Expected a short project-relative file path.",
    )
    p = PurePosixPath(value)
    require(
        p.parts
        and not p.is_absolute()
        and str(p) == value
        and not any(x in {".", ".."} for x in p.parts),
        "Paths must be normalized and stay inside the project.",
    )
    require(
        not any(ord(c) < 32 for c in value) and not any(c in value for c in "\\:"),
        "Unsupported path characters.",
    )
    return value


def local(root, value):
    p = root / relative(value)
    no_links(p)
    return p


def read_bytes(path, limit=MAX_FILE):
    no_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        require(
            stat.S_ISREG(os.fstat(handle.fileno()).st_mode),
            "Only regular files are supported.",
        )
        before = os.fstat(handle.fileno())
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        require(
            (before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_ino, after.st_size, after.st_mtime_ns),
            "File changed while it was being read.",
        )
    require(len(data) <= limit, "File exceeds the bounded local size limit.")
    return data


def read_json(path, limit=1024 * 1024):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON keys are not accepted.")
            result[key] = value
        return result

    def bad_constant(value):
        raise WorkflowError("Non-finite JSON values are not accepted.")

    return json.loads(
        read_bytes(path, limit),
        object_pairs_hook=pairs,
        parse_constant=bad_constant,
    )


def create(path, data):
    no_links(path)
    require(path.parent.is_dir(), "Output parent must already exist.")
    # Exclusive creation also refuses an existing empty destination.
    with path.open("xb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def write_json(path, value):
    create(
        path,
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode()
        + b"\n",
    )


def load_plan(path):
    path = Path(os.path.abspath(path))
    plan = read_json(path)
    require(
        isinstance(plan, dict)
        and set(plan) == {"schema_version", "title", "facts", "steps"},
        "Unexpected analysis-plan fields.",
    )
    require(
        plan["schema_version"] == "1.0"
        and isinstance(plan["title"], str)
        and len(plan["title"]) <= 200,
        "Unsupported plan version or title.",
    )
    require(
        isinstance(plan["facts"], dict) and len(plan["facts"]) <= 30,
        "Use a small fact record.",
    )
    for name, fact in plan["facts"].items():
        require(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name), "Invalid fact name.")
        require(
            isinstance(fact, dict)
            and set(fact) == {"value", "source", "note", "evidence"},
            "Invalid fact fields.",
        )
        require(
            fact["source"] in {"unknown", "user", "file"}
            and isinstance(fact["note"], str)
            and len(fact["note"]) <= 2000,
            "Facts need a declared source and short note.",
        )
        require(
            isinstance(fact["evidence"], dict) and len(fact["evidence"]) <= 20,
            "Invalid fact evidence.",
        )
        for filename, sha in fact["evidence"].items():
            relative(filename)
            require(
                isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha),
                "Invalid evidence digest.",
            )
    require(
        isinstance(plan["steps"], list) and 1 <= len(plan["steps"]) <= 12,
        "Use one to twelve ordered steps.",
    )
    seen, written, producers, ancestors = set(), set(), {}, {}
    fields = {
        "id",
        "skill",
        "inputs",
        "parameters",
        "fact_parameters",
        "required_facts",
        "depends_on",
        "result",
        "outputs",
        "receipt",
        "tool_versions",
    }
    for step in plan["steps"]:
        require(
            isinstance(step, dict) and set(step) == fields, "Unexpected step fields."
        )
        name = step["id"]
        require(
            isinstance(name, str)
            and re.fullmatch(r"[a-z][a-z0-9-]{0,40}", name)
            and name not in seen,
            "Step IDs must be unique.",
        )
        require(
            step["skill"] in TOOLS,
            "This companion does not yet check that helper's native result.",
        )
        require(
            isinstance(step["depends_on"], list) and set(step["depends_on"]) <= seen,
            "Dependencies must name earlier steps; cycles are unsupported.",
        )
        require(
            isinstance(step["required_facts"], list)
            and set(step["required_facts"]) <= set(plan["facts"]),
            "Required facts must be declared.",
        )
        for key in ["inputs", "parameters", "fact_parameters", "tool_versions"]:
            require(
                isinstance(step[key], dict) and len(step[key]) <= 30,
                "Step configuration must be small objects.",
            )
        require(
            step["inputs"] and all(isinstance(k, str) for k in step["inputs"]),
            "Declare native input hash keys.",
        )
        require(
            set(step["fact_parameters"].values()) <= set(step["required_facts"]),
            "Parameter facts must be required facts.",
        )
        require(
            set(step["fact_parameters"]) <= set(step["parameters"]),
            "Fact bindings must reference declared parameters.",
        )
        require(
            isinstance(step["outputs"], list)
            and 1 <= len(step["outputs"]) <= 30
            and step["result"] in step["outputs"],
            "Outputs must include the native result JSON.",
        )
        require(
            len(step["outputs"]) == len(set(step["outputs"])), "Duplicate output paths."
        )
        for value in (
            list(step["inputs"].values()) + step["outputs"] + [step["receipt"]]
        ):
            relative(value)
        outputs = set(step["outputs"]) | {step["receipt"]}
        require(
            step["receipt"] not in step["outputs"]
            and not outputs & (written | set(step["inputs"].values()) | {path.name}),
            "Outputs and receipts must be distinct from inputs, other steps and the plan.",
        )
        ancestors[name] = set(step["depends_on"])
        for parent in step["depends_on"]:
            ancestors[name].update(ancestors[parent])
        for filename in step["inputs"].values():
            require(
                filename not in producers or producers[filename] in ancestors[name],
                "Declare the producing step as a dependency for intermediate inputs.",
            )
        for filename in outputs:
            require(
                not any(
                    filename in earlier["inputs"].values()
                    for earlier in plan["steps"]
                    if earlier["id"] in seen
                ),
                "A later output cannot overwrite an earlier input.",
            )
            producers[filename] = name
        written.update(outputs)
        seen.add(name)
    for fact in plan["facts"].values():
        require(
            not set(fact["evidence"]) & written,
            "Bind facts to source inputs, not changing workflow outputs.",
        )
    return path.parent, plan


def fact_problem(root, fact):
    if (
        fact["source"] == "unknown"
        or fact["value"] is None
        or fact["value"] == ""
        or not fact["note"]
        or not fact["evidence"]
    ):
        return "unconfirmed"
    for name, sha in fact["evidence"].items():
        try:
            if digest(read_bytes(local(root, name))) != sha:
                return "evidence-changed"
        except (OSError, ValueError):
            return "evidence-unavailable"
    return None


def identity(skill):
    from validate_skeleton import package_digest

    package = ROOT / "skills" / skill
    manifest = read_json(package / "manifest.json")
    entry = next(
        x for x in read_json(ROOT / "registry.json")["skills"] if x["name"] == skill
    )
    require(
        package_digest(package) == entry["package_digest"],
        "Installed package differs from its registry identity.",
    )
    return {
        "skill": skill,
        "package_version": manifest["version"],
        "package_digest": entry["package_digest"],
        "tool": {
            "name": TOOLS[skill],
            "version": manifest["script_verification"].get(
                "artifact_version", manifest["version"]
            ),
        },
    }


def context(root, plan, step, previous):
    inputs = {k: digest(read_bytes(local(root, v))) for k, v in step["inputs"].items()}
    return {
        "workflow_version": VERSION,
        "step": step,
        "facts": {k: plan["facts"][k] for k in step["required_facts"]},
        "inputs": inputs,
        "package": identity(step["skill"]),
        "dependencies": {k: previous[k]["receipt_sha256"] for k in step["depends_on"]},
    }


def native_check(root, step, ctx):
    data = read_json(local(root, step["result"]), limit=MAX_FILE)
    if step["skill"] == "count-based-differential-expression":
        require(isinstance(data, dict) and data.get("method") == "DESeq2" and data.get("adapter_version") == ctx["package"]["tool"]["version"], "Expected the exact bounded DESeq2 adapter result.")
        require(isinstance(data.get("model"), dict), "DESeq2 model metadata is missing.")
        data = {**data, "tool": ctx["package"]["tool"], "runtime_versions": data["model"].get("versions", {})}
        from importlib.util import spec_from_file_location, module_from_spec
        path = ROOT / "skills" / step["skill"] / "scripts/run_count_de.py"
        spec = spec_from_file_location("goose_checked_de", path)
        module = module_from_spec(spec)
        previous_bytecode_policy = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous_bytecode_policy
        require(data.get("worker_sha256") == digest(module.WORKER.encode()), "DESeq2 worker identity mismatch.")
    if step["skill"] == "protein-level-differential-abundance":
        require(isinstance(data, dict) and isinstance(data.get("tool"), dict), "Protein model metadata is missing.")
        tool = data["tool"]
        require({k: tool.get(k) for k in ("name", "version")} == ctx["package"]["tool"], "Protein helper identity differs.")
        from importlib.util import spec_from_file_location, module_from_spec
        path = ROOT / "skills" / step["skill"] / "scripts/run_limma.py"
        spec = spec_from_file_location("goose_checked_protein", path)
        module = module_from_spec(spec)
        previous_bytecode_policy = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous_bytecode_policy
        require(tool.get("worker_sha256") == module.bundled_worker()[1], "Protein worker identity mismatch.")
        require(data.get("runtime_versions") == {"R": tool.get("r_version"), "limma": tool.get("limma_version")}, "Protein runtime versions disagree.")
        data = {**data, "tool": ctx["package"]["tool"]}
    require(
        isinstance(data, dict) and data.get("status") in OUTCOMES,
        "Missing or unsupported native result status.",
    )
    require(
        data.get("tool") == ctx["package"]["tool"],
        "Native result tool/version differs from the selected helper.",
    )
    input_hashes = data.get("input_sha256")
    handoff_status = data["status"]
    if step["skill"] == "bioinformatics-qc-and-publication-reporting":
        require(
            isinstance(data.get("sources"), list)
            and isinstance(data.get("figures"), list),
            "Report source inventory is missing.",
        )
        input_hashes = {}
        for source in data["sources"]:
            require(
                isinstance(source, dict) and isinstance(source.get("label"), str),
                "Invalid report source.",
            )
            key = "source:" + source["label"]
            require(key not in input_hashes, "Duplicate report source label.")
            input_hashes[key] = source.get("sha256")
        for figure in data["figures"]:
            require(
                isinstance(figure, dict) and isinstance(figure.get("label"), str),
                "Invalid report figure.",
            )
            key = "figure:" + figure["label"]
            require(key not in input_hashes, "Duplicate report figure label.")
            input_hashes[key] = figure.get("metadata_sha256")
            input_hashes["png:" + figure["label"]] = figure.get("png_sha256")
        expected = (
            "completed"
            if data["sources"]
            and all(x.get("status") == "completed" for x in data["sources"])
            else "partial"
        )
        require(
            data.get("source_outcome") == expected,
            "Report summary conflicts with source outcomes.",
        )
        if expected != "completed":
            handoff_status = "partial"
    require(
        input_hashes == ctx["inputs"],
        "Native result inputs do not match the declared current files.",
    )
    config = data.get("config", {})
    require(isinstance(config, dict), "Native parameters must be an object.")
    require(
        all(k in config and config[k] == v for k, v in step["parameters"].items()),
        "Native result parameters differ from the plan.",
    )
    versions = data.get("runtime_versions", data.get("versions", {}))
    require(
        isinstance(versions, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in versions.items()),
        "Native runtime versions must be a string mapping.",
    )
    require(
        all(versions.get(k) == v for k, v in step["tool_versions"].items()),
        "Native runtime versions differ from the declared environment.",
    )
    outputs = set(step["outputs"])
    directory = PurePosixPath(step["result"]).parent
    native_files = data.get("files", [])
    require(
        isinstance(native_files, list) and len(native_files) <= 100,
        "Invalid native output inventory.",
    )
    for name in native_files:
        outputs.add(str(directory / relative(name)))
    artifacts = {v: digest(read_bytes(local(root, v))) for v in sorted(outputs)}
    output_hashes = data.get("output_sha256", {})
    require(isinstance(output_hashes, dict) and len(output_hashes) <= 100, "Invalid native output digest inventory.")
    for name, sha in output_hashes.items():
        require(artifacts.get(str(directory / relative(name))) == sha, "Native output file differs from its retained digest.")
    object_names = {
        "goose_single_cell_qc": "checked.h5ad",
        "goose_single_cell_core": "processed.h5ad",
    }
    if data["tool"]["name"] in object_names:
        object_path = str(directory / object_names[data["tool"]["name"]])
        require(
            object_path in artifacts
            and artifacts[object_path] == data.get("output_object_sha256"),
            "Native checked object digest does not match the retained object.",
        )
    if data["tool"]["name"] == "goose_qc_report":
        for source in data["sources"]:
            copied = str(directory / relative(source.get("file")))
            require(
                artifacts.get(copied) == source.get("sha256"),
                "Copied report source is missing or differs from its source digest.",
            )
    return {
        "native_status": data["status"],
        "handoff_status": handoff_status,
        "open_items": data.get("unresolved", []),
        "runtime_versions": versions,
        "artifacts": artifacts,
    }


def evaluate(root, plan):
    previous = {}
    for step in plan["steps"]:
        row = {
            "id": step["id"],
            "skill": step["skill"],
            "status": "ready",
            "reason": "No checked receipt yet.",
            "outputs": [],
        }
        previous[step["id"]] = row
        gaps = [
            k for k in step["required_facts"] if fact_problem(root, plan["facts"][k])
        ]
        if gaps:
            row.update(
                status="needs-decision",
                reason=f"Confirm or refresh fact: {gaps[0]}",
                question=QUESTIONS.get(
                    gaps[0], f"请补充 {gaps[0]}，说明来源和适用的数据。"
                ),
            )
            continue
        conflicts = [
            k
            for k, f in step["fact_parameters"].items()
            if step["parameters"][k] != plan["facts"][f]["value"]
        ]
        if conflicts:
            row.update(
                status="needs-decision",
                reason=f"Parameter conflicts with confirmed fact: {conflicts[0]}",
                question="计划参数与已确认事实不一致，请核对后再继续。",
            )
            continue
        reporting = step["skill"] == "bioinformatics-qc-and-publication-reporting"
        if any(
            not (
                previous[k]["status"] == "completed"
                or (
                    reporting
                    and previous[k]["status"] in OUTCOMES
                    and "receipt_sha256" in previous[k]
                )
            )
            for k in step["depends_on"]
        ):
            row.update(
                status="blocked", reason="An upstream step is incomplete or stale."
            )
            continue
        try:
            ctx = context(root, plan, step, previous)
        except (OSError, ValueError) as exc:
            row.update(status="needs-input", reason=str(exc))
            continue
        receipt = local(root, step["receipt"])
        if not receipt.exists():
            continue
        try:
            saved = read_json(receipt)
            require(isinstance(saved, dict), "Invalid receipt object.")
            require(
                saved.get("schema_version") == "1.0"
                and saved.get("context_sha256") == digest(canonical(ctx))
                and saved.get("context") == ctx,
                "Inputs, facts, parameters, package or upstream receipt changed.",
            )
            if saved.get("reported_failure"):
                require(
                    isinstance(saved.get("note"), str) and saved["note"].strip(),
                    "Failure record requires a note.",
                )
                row.update(
                    status="blocked-or-failed",
                    reason="Reported failure: " + saved["note"],
                )
                continue
            current = native_check(root, step, ctx)
            require(
                saved.get("result") == current,
                "Recorded outputs or runtime metadata changed.",
            )
            row.update(
                status=current["handoff_status"],
                reason="Checked native result; only completed steps may feed downstream analysis.",
                outputs=list(current["artifacts"]),
                receipt_sha256=digest(read_bytes(receipt)),
            )
            if current["handoff_status"] in {"needs-decision", "needs-review"}:
                row["reason"] = "Inspect unresolved native result: " + str(
                    current["open_items"]
                )
                if current["open_items"]:
                    item = current["open_items"][0]
                    questions = {
                        "condition": "样本分别属于哪一组？请补充按 sample_id 对应的分组表，不要根据样本标题猜测。",
                        "data-scale": QUESTIONS["scale"],
                        "missing-measurements": "矩阵存在缺失值；请确认它们的含义和适用的处理方法，再进行下游分析。",
                    }
                    native_question = item.get("question") if isinstance(item, dict) else None
                    if isinstance(native_question, str) and native_question.strip():
                        row["question"] = native_question
                        row["reason"] = "Native analysis requires a decision before quantification."
                    else:
                        row["question"] = questions.get(
                            str(item), "请核对原始结果中第一个未解决事项：" + str(item)
                        )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            row.update(status="stale", reason=str(exc))
    rows = list(previous.values())
    return {
        "schema_version": "1.0",
        "tool_version": VERSION,
        "title": plan["title"],
        "status": (
            "completed"
            if all(r["status"] == "completed" for r in rows)
            else "incomplete"
        ),
        "steps": rows,
        "next_action": next((r for r in rows if r["status"] != "completed"), None),
        "network_performed": False,
    }


def record(root, plan, step_id):
    state = evaluate(root, plan)
    rows = {r["id"]: r for r in state["steps"]}
    require(step_id in rows, "Unknown step.")
    row = rows[step_id]
    require(
        row["status"] not in {"needs-input", "blocked"} and not row.get("question"),
        "Resolve missing facts, inputs or upstream results before recording.",
    )
    step = next(s for s in plan["steps"] if s["id"] == step_id)
    ctx = context(root, plan, step, rows)
    result = native_check(root, step, ctx)
    receipt = {
        "schema_version": "1.0",
        "tool_version": VERSION,
        "context_sha256": digest(canonical(ctx)),
        "context": ctx,
        "result": result,
    }
    require(context(root, plan, step, rows) == ctx, "Inputs changed during recording.")
    write_json(local(root, step["receipt"]), receipt)
    return {
        "status": "recorded",
        "step": step_id,
        "native_status": result["native_status"],
        "receipt": step["receipt"],
    }


def note_failure(root, plan, step_id, note):
    require(
        isinstance(note, str) and 0 < len(note.strip()) <= 2000,
        "Provide a short failure explanation.",
    )
    rows = {r["id"]: r for r in evaluate(root, plan)["steps"]}
    require(
        step_id in rows
        and rows[step_id]["status"] not in {"needs-decision", "needs-input", "blocked"},
        "Resolve input/fact/upstream gaps first; their state is already visible.",
    )
    step = next(s for s in plan["steps"] if s["id"] == step_id)
    ctx = context(root, plan, step, rows)
    write_json(
        local(root, step["receipt"]),
        {
            "schema_version": "1.0",
            "tool_version": VERSION,
            "context": ctx,
            "context_sha256": digest(canonical(ctx)),
            "reported_failure": True,
            "note": note,
        },
    )
    return {
        "status": "recorded",
        "native_status": "not-available",
        "reported_failure": True,
    }


def confirm(root, plan, name, value, source, note, evidence, output):
    require(
        PurePosixPath(relative(output)).parent == PurePosixPath("."),
        "Save the new plan beside the current plan so relative input paths keep their meaning.",
    )
    require(
        name in plan["facts"] and note.strip() and evidence,
        "Choose a declared fact, explain its source and bind it to input files.",
    )
    plan["facts"][name] = {
        "value": value,
        "source": source,
        "note": note,
        "evidence": {p: digest(read_bytes(local(root, p))) for p in evidence},
    }
    write_json(local(root, output), plan)
    return {"status": "recorded", "plan": output, "fact": name}


def overview(root, state, output):
    def escape(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("|", "&#124;")
            .replace("\n", " ")
            .replace("[", "&#91;")
            .replace("]", "&#93;")
        )

    labels = {
        "completed": "已完成",
        "ready": "待执行",
        "needs-decision": "待补充",
        "needs-review": "待审核",
        "needs-input": "缺少输入",
        "needs-tool": "缺少工具",
        "stale": "需重新检查",
        "blocked": "等待上游",
        "partial": "部分完成",
        "blocked-or-failed": "执行失败",
        "invalid-input": "输入不符合要求",
        "invalid-output": "输出不符合要求",
    }
    names = {
        "goose_deseq2": "原始计数差异分析",
        "goose_microarray_limma": "微阵列表达差异分析",
        "goose_protein_table_qc": "蛋白定量表检查",
        "protein-level-differential-abundance": "蛋白差异丰度分析",
        "goose_pcoa": "距离矩阵 PCoA",
        "goose_qpcr": "qPCR 相对表达与 QC",
        "goose_independent_2x2": "独立样本 2×2 分类比较",
        "goose_local_id_mapping": "注释准备与 ID 映射",
        "goose_local_ora": "候选基因集富集",
        "goose_gseapy_prerank": "排序基因集富集",
        "goose_sample_validation": "样本与设计检查",
        "goose_two_group": "两组比较",
        "goose_geo_preparation": "表达矩阵准备",
        "goose_single_cell_qc": "单细胞 QC",
        "goose_single_cell_core": "单细胞探索分析",
        "goose_marker_evidence": "细胞类型候选证据",
        "goose_single_cell_pseudobulk": "按样本汇总计数",
        "goose_result_visualization": "图表",
        "goose_qc_report": "分析报告",
    }
    advice = {
        "completed": "原生结果与当前输入、参数和回执匹配。",
        "ready": "按原 Skill 核对方法适用性，执行后登记结果。",
        "needs-decision": "补充会影响结果的关键事实。",
        "needs-review": "查看候选证据并补充必要的领域判断。",
        "needs-input": "补齐输入文件，核对其来源和版本。",
        "needs-tool": "准备原 Skill 声明的工具后继续。",
        "stale": "输入、参数、版本或产物需要重新检查；重跑时使用新路径。",
        "blocked": "先解决上游未完成或已失效的步骤。",
        "partial": "查看原始结果中的未完成事项，不作为完成分析继续推断。",
        "blocked-or-failed": "查看失败说明，修复后使用新回执重试。",
    }
    destination = local(root, output)
    lines = [
        "# 分析进度与结果入口",
        "",
        escape(state["title"]),
        "",
        f"已完成 {sum(r['status'] == 'completed' for r in state['steps'])} / {len(state['steps'])} 项；未解决事项继续保留。",
        "",
        "| 步骤 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for row in state["steps"]:
        lines.append(
            f"| {escape(names[TOOLS[row['skill']]])} | {escape(labels.get(row['status'], row['status']))} | {escape(row.get('question', advice.get(row['status'], row['reason'])))} |"
        )
    lines += [
        "",
        "## 下一步",
        "",
        escape(
            (state["next_action"] or {}).get(
                "question",
                advice.get(
                    (state["next_action"] or {}).get("status"), "全部声明步骤已完成。"
                ),
            )
        ),
        "",
        "## 已检查的产物",
        "",
    ]
    for row in state["steps"]:
        for name in row["outputs"]:
            href = quote(os.path.relpath(root / name, destination.parent), safe="/")
            lines.append(
                f"- {escape(names[TOOLS[row['skill']]])}: [{escape(name)}]({href})"
            )
    lines += [
        "",
        "此文件是生成时的快照。继续分析前重新检查状态；它不替代原始 QC、方法记录或科学判断。",
        "",
    ]
    create(destination, "\n".join(lines).encode())
    return {"status": "completed", "output": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["status", "record", "confirm", "overview", "note-failure"]
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--step")
    parser.add_argument("--fact")
    parser.add_argument("--value", help="JSON value, e.g. a quoted string or true")
    parser.add_argument("--source", choices=["user", "file"], default="user")
    parser.add_argument("--note", default="")
    parser.add_argument("--evidence", nargs="+", default=[])
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        root, plan = load_plan(args.plan)
        if args.action == "record":
            result = record(root, plan, args.step)
        elif args.action == "note-failure":
            result = note_failure(root, plan, args.step, args.note)
        elif args.action == "confirm":
            require(
                args.output and args.value is not None,
                "Confirm requires a new --output plan and JSON --value.",
            )
            result = confirm(
                root,
                plan,
                args.fact,
                json.loads(args.value),
                args.source,
                args.note,
                args.evidence,
                args.output,
            )
        else:
            result = evaluate(root, plan)
            if args.action == "overview":
                require(args.output, "Overview requires a new --output file.")
                result = overview(root, result, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        print(
            json.dumps(
                {"status": "invalid-input", "error": str(exc)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
