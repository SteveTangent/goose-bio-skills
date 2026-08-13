#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay retained, offline minimum-reliability checks for Wave R3."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "research-wave-r3-minimal-v0.1.json"
VERSION = "0.1.0"
PACKAGES = {
    "tree_qc": "phylogenetic-tree-io-and-qc",
    "metabolomics_qc": "untargeted-metabolomics-feature-table-qc",
    "read_alignment": "read-alignment-selection-and-execution",
}
SCRIPTS = {
    "tree_qc": ROOT / "skills" / PACKAGES["tree_qc"] / "scripts" / "qc_newick_tree.py",
    "metabolomics_qc": ROOT / "skills" / PACKAGES["metabolomics_qc"] / "scripts" / "qc_metabolomics_feature_table.py",
    "read_alignment": ROOT / "skills" / PACKAGES["read_alignment"] / "scripts" / "run_short_dna_alignment.py",
}
LEGAL_PREFIXES = (
    "LICENSE", "NOTICE", "COPYING", "COPYRIGHT", "ATTRIBUTION",
    "THIRD_PARTY_NOTICES", "THIRD-PARTY-NOTICES",
)
CODE_SUFFIXES = {".py", ".r", ".sh", ".bash", ".zsh", ".pl", ".rb", ".js", ".ts"}


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(message)
        self.count += 1


def strict_json_loads(payload: str | bytes) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(payload, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def package_digest(package: Path) -> str:
    projection: list[dict[str, str]] = []
    for path in sorted(item for item in package.rglob("*") if item.is_file()):
        relative = path.relative_to(package)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        upper_name = relative.name.upper()
        if upper_name.startswith(LEGAL_PREFIXES):
            kind = "license"
        elif relative.as_posix() in {"manifest.json", "agents/interface.yaml"}:
            kind = "metadata"
        elif relative.parts[0] == "scripts" or relative.suffix.lower() in CODE_SUFFIXES:
            kind = "code"
        else:
            kind = "text"
        projection.append({"kind": kind, "path": relative.as_posix(), "sha256": sha256_file(path)})
    encoded = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def run_cli(script: Path, arguments: list[str], cwd: Path, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def parse_event(text: str) -> dict[str, Any]:
    lines = text.strip().splitlines()
    if len(lines) != 1:
        raise RuntimeError("helper did not emit exactly one JSON event")
    event = strict_json_loads(lines[0])
    if not isinstance(event, dict):
        raise RuntimeError("helper event is not an object")
    return event


def materialize(case: dict[str, Any], directory: Path, checks: Checks) -> Path:
    payload = case["content"].encode("utf-8")
    checks.require(sha256_bytes(payload) == case["sha256"], f"fixture hash differs: {case['filename']}")
    path = directory / case["filename"]
    path.write_bytes(payload)
    checks.require(path.read_bytes() == payload, f"fixture materialization differs: {case['filename']}")
    return path


def check_self_tests(fixture: dict[str, Any], root: Path, checks: Checks) -> None:
    for key, script in SCRIPTS.items():
        completed = run_cli(script, ["--self-test"], root)
        checks.require(completed.returncode == 0, f"{key} self-test failed: {completed.stderr}")
        event = parse_event(completed.stdout)
        expected = {
            "checks": fixture[key]["self_test_checks"],
            "status": "pass",
            "version": "0.8.0",
        }
        if key == "read_alignment":
            expected["real_minimap2_runtime"] = "not-evaluated"
        checks.require(event == expected, f"{key} self-test event differs")


def check_package_bindings(fixture: dict[str, Any], checks: Checks) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, name in PACKAGES.items():
        digest = package_digest(ROOT / "skills" / name)
        checks.require(digest == fixture[key]["package_digest"], f"{name} package digest differs")
        result[name] = digest
    return result


def check_tree(case: dict[str, Any], root: Path, checks: Checks) -> str:
    tree = materialize(case["tree"], root, checks)
    comparison = materialize(case["comparison"], root, checks)
    invalid = materialize(case["invalid_tree"], root, checks)

    def arguments(input_path: Path, output: str) -> list[str]:
        return ["--tree", input_path.name, "--compare-tree", comparison.name, "--output", output]

    first = run_cli(SCRIPTS["tree_qc"], arguments(tree, "tree-1.json"), root)
    second = run_cli(SCRIPTS["tree_qc"], arguments(tree, "tree-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "tree valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "tree completion differs")
    first_bytes = (root / "tree-1.json").read_bytes()
    second_bytes = (root / "tree-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "tree repeat bytes differ")
    output_hash = sha256_bytes(first_bytes)
    checks.require(output_hash == case["expected"]["output_sha256"], f"tree output hash differs: {output_hash}")
    report = strict_json_loads(first_bytes)
    summary = report["tree"]["summary"]
    checks.require(summary["tip_count"] == case["expected"]["tip_count"], "tree tip count differs")
    checks.require(summary["internal_node_count"] == case["expected"]["internal_node_count"], "tree internal count differs")
    checks.require(summary["polytomy_count"] == case["expected"]["polytomy_count"], "tree polytomy count differs")
    checks.require(report["tip_set_comparison"]["status"] == case["expected"]["tip_set_status"], "tree tip-set status differs")
    before = sha256_file(root / "tree-1.json")
    overwrite = run_cli(SCRIPTS["tree_qc"], arguments(tree, "tree-1.json"), root)
    checks.require(overwrite.returncode == 2, "tree overwrite was accepted")
    checks.require(parse_event(overwrite.stderr).get("error", {}).get("code") == "output-exists", "tree overwrite classification differs")
    checks.require(sha256_file(root / "tree-1.json") == before, "tree overwrite changed output")
    rejected = run_cli(SCRIPTS["tree_qc"], ["--tree", invalid.name, "--output", "tree-invalid.json"], root)
    checks.require(rejected.returncode == 2, "tree duplicate tips were accepted")
    checks.require(parse_event(rejected.stderr).get("error", {}).get("code") == case["invalid_tree"]["expected_error"], "tree invalid classification differs")
    checks.require(not (root / "tree-invalid.json").exists(), "tree invalid run created output")
    return output_hash


def metabolomics_arguments(case: dict[str, Any], feature: Path, metadata: Path, output: str) -> list[str]:
    config = case["arguments"]
    return [
        "--feature-table", feature.name,
        "--metadata", metadata.name,
        "--output", output,
        "--intensity-semantics", config["intensity_semantics"],
        "--missing-token", config["missing_token"],
        "--zero-semantics", config["zero_semantics"],
    ]


def check_metabolomics(case: dict[str, Any], root: Path, checks: Checks) -> str:
    feature = materialize(case["feature_table"], root, checks)
    metadata = materialize(case["metadata"], root, checks)
    invalid = materialize(case["invalid_feature_table"], root, checks)
    first = run_cli(SCRIPTS["metabolomics_qc"], metabolomics_arguments(case, feature, metadata, "metabolomics-1.json"), root)
    second = run_cli(SCRIPTS["metabolomics_qc"], metabolomics_arguments(case, feature, metadata, "metabolomics-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "metabolomics valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "metabolomics completion differs")
    first_bytes = (root / "metabolomics-1.json").read_bytes()
    second_bytes = (root / "metabolomics-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "metabolomics repeat bytes differ")
    output_hash = sha256_bytes(first_bytes)
    checks.require(output_hash == case["expected"]["output_sha256"], f"metabolomics output hash differs: {output_hash}")
    report = strict_json_loads(first_bytes)
    checks.require(report["feature_qc"]["feature_count"] == case["expected"]["feature_count"], "metabolomics feature count differs")
    checks.require(report["joins"]["matched_sample_count"] == case["expected"]["sample_count"], "metabolomics sample count differs")
    sample_qc = {item["sample_id"]: item for item in report["sample_qc"]}
    checks.require(sample_qc["S2"]["detected_feature_count"] == case["expected"]["s2_detected_feature_count"], "metabolomics detected count differs")
    checks.require(sample_qc["S2"]["total_missing_feature_count"] == case["expected"]["s2_total_missing_feature_count"], "metabolomics missing count differs")
    feature_qc = {item["feature_id"]: item for item in report["feature_qc"]["features"]}
    checks.require(feature_qc["F2"]["pooled_qc_rsd"]["rsd_percent"] == case["expected"]["f2_pooled_qc_rsd_percent"], "metabolomics RSD differs")
    before = sha256_file(root / "metabolomics-1.json")
    overwrite = run_cli(SCRIPTS["metabolomics_qc"], metabolomics_arguments(case, feature, metadata, "metabolomics-1.json"), root)
    checks.require(overwrite.returncode != 0, "metabolomics overwrite was accepted")
    checks.require(sha256_file(root / "metabolomics-1.json") == before, "metabolomics overwrite changed output")
    rejected = run_cli(SCRIPTS["metabolomics_qc"], metabolomics_arguments(case, invalid, metadata, "metabolomics-invalid.json"), root)
    checks.require(rejected.returncode == 2, "metabolomics negative value was accepted")
    error = parse_event(rejected.stderr)
    codes = [item.get("code") for item in error.get("issues", [])]
    checks.require(case["invalid_feature_table"]["expected_issue"] in codes, "metabolomics invalid classification differs")
    checks.require(not (root / "metabolomics-invalid.json").exists(), "metabolomics invalid run created output")
    return output_hash


def check_alignment(case: dict[str, Any], root: Path, checks: Checks) -> None:
    reference = materialize(case["reference"], root, checks)
    reads = materialize(case["reads"], root, checks)
    missing_tool = root / "missing-minimap2"

    def arguments(declared: bool) -> list[str]:
        result = [
            "--reference", reference.name,
            "--reads", reads.name,
            "--minimap2", str(missing_tool),
            "--minimap2-sha256", "0" * 64,
            "--output-sam", "alignment.sam",
            "--output-report", "alignment.json",
        ]
        if declared:
            result.append("--declared-single-end-short-genomic-dna")
        return result

    unavailable = run_cli(SCRIPTS["read_alignment"], arguments(True), root)
    checks.require(unavailable.returncode == 3, "unavailable minimap2 did not fail closed")
    event = parse_event(unavailable.stderr)
    checks.require(event.get("status") == case["expected"]["unavailable_tool_status"], "alignment unavailable status differs")
    checks.require(event.get("code") == case["expected"]["unavailable_tool_code"], "alignment unavailable code differs")
    checks.require(not (root / "alignment.sam").exists() and not (root / "alignment.json").exists(), "unavailable alignment created output")
    undeclared = run_cli(SCRIPTS["read_alignment"], arguments(False), root)
    checks.require(undeclared.returncode == 2, "missing assay declaration was accepted")
    event = parse_event(undeclared.stderr)
    checks.require(event.get("status") == case["expected"]["missing_declaration_status"], "alignment declaration status differs")
    checks.require(event.get("code") == case["expected"]["missing_declaration_code"], "alignment declaration code differs")


def main() -> int:
    fixture = strict_json_loads(FIXTURE.read_bytes())
    checks = Checks()
    package_bindings = check_package_bindings(fixture, checks)
    with tempfile.TemporaryDirectory(prefix="bio02-wave-r3-minimum-") as temporary:
        root = Path(temporary)
        check_self_tests(fixture, root, checks)
        tree_hash = check_tree(fixture["tree_qc"], root, checks)
        metabolomics_hash = check_metabolomics(fixture["metabolomics_qc"], root, checks)
        check_alignment(fixture["read_alignment"], root, checks)
    print(json.dumps({
        "checks": checks.count,
        "fixture_sha256": sha256_file(FIXTURE),
        "network_performed": False,
        "output_sha256": {
            PACKAGES["tree_qc"]: tree_hash,
            PACKAGES["metabolomics_qc"]: metabolomics_hash,
        },
        "package_digests": package_bindings,
        "real_minimap2_runtime": "not-evaluated",
        "status": "pass",
        "version": VERSION,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "status": "fail", "version": VERSION}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
