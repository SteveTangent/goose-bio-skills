#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay retained, offline minimum-reliability checks for Wave R2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_skeleton import package_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "research-wave-r2-minimal-v0.4.json"
VERSION = "0.4.0"
PACKAGES = {
    "amplicon_qc": "amplicon-feature-table-and-taxonomy-qc",
    "peak_qc": "chromatin-peak-set-qc",
    "protein_da": "protein-level-differential-abundance",
}
SCRIPTS = {
    "amplicon_qc": ROOT / "skills" / PACKAGES["amplicon_qc"] / "scripts" / "qc_amplicon_tables.py",
    "peak_qc": ROOT / "skills" / PACKAGES["peak_qc"] / "scripts" / "check_peak_sets.py",
    "protein_da": ROOT / "skills" / PACKAGES["protein_da"] / "scripts" / "run_limma.py",
}


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


def run_cli(script: Path, arguments: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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
        completed = run_cli(script, ["--self-test"], root, timeout=90)
        checks.require(completed.returncode == 0, f"{key} self-test failed: {completed.stderr}")
        event = parse_event(completed.stdout)
        checks.require(event == {
            "checks": fixture[key]["self_test_checks"],
            "status": "pass",
            "version": fixture[key].get("artifact_version", "0.9.0"),
        }, f"{key} self-test event differs")


def check_package_bindings(fixture: dict[str, Any], checks: Checks) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, name in PACKAGES.items():
        digest = package_digest(ROOT / "skills" / name)
        checks.require(digest == fixture[key]["package_digest"], f"{name} package digest differs")
        result[name] = digest
    return result


def check_amplicon(case: dict[str, Any], root: Path, checks: Checks) -> str:
    feature = materialize(case["feature_table"], root, checks)
    metadata = materialize(case["metadata"], root, checks)
    taxonomy = materialize(case["taxonomy"], root, checks)
    invalid = materialize(case["invalid_feature_table"], root, checks)
    config = case["arguments"]

    def arguments(input_path: Path, output: str) -> list[str]:
        return [
            "--feature-table", str(input_path), "--metadata", str(metadata),
            "--taxonomy", str(taxonomy), "--output", output,
            "--metadata-sample-column", config["metadata_sample_column"],
            "--negative-control-column", config["negative_control_column"],
            "--negative-control-value", config["negative_control_value"],
        ]

    first = run_cli(SCRIPTS["amplicon_qc"], arguments(feature, "amplicon-1.json"), root)
    second = run_cli(SCRIPTS["amplicon_qc"], arguments(feature, "amplicon-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "amplicon valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "amplicon completion differs")
    first_bytes = (root / "amplicon-1.json").read_bytes()
    second_bytes = (root / "amplicon-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "amplicon repeat bytes differ")
    output_hash = sha256_bytes(first_bytes)
    checks.require(output_hash == case["expected"]["output_sha256"], f"amplicon output hash differs: {output_hash}")
    report = strict_json_loads(first_bytes)
    checks.require(report["feature_qc"]["feature_count"] == case["expected"]["feature_count"], "amplicon feature count differs")
    checks.require(report["joins"]["feature_table_sample_count"] == case["expected"]["sample_count"], "amplicon sample count differs")
    checks.require(report["sample_qc"]["zero_depth_sample_ids"] == case["expected"]["zero_depth_samples"], "amplicon zero-depth samples differ")
    before = sha256_file(root / "amplicon-1.json")
    overwrite = run_cli(SCRIPTS["amplicon_qc"], arguments(feature, "amplicon-1.json"), root)
    checks.require(overwrite.returncode != 0, "amplicon overwrite was accepted")
    checks.require(sha256_file(root / "amplicon-1.json") == before, "amplicon overwrite changed output")
    rejected = run_cli(SCRIPTS["amplicon_qc"], arguments(invalid, "amplicon-invalid.json"), root)
    checks.require(rejected.returncode == 2, "amplicon invalid count was accepted")
    error = parse_event(rejected.stderr)
    codes = [item.get("code") for item in error.get("issues", [])]
    checks.require(error.get("status") == "invalid-input" and case["invalid_feature_table"]["expected_issue"] in codes, "amplicon invalid classification differs")
    checks.require(not (root / "amplicon-invalid.json").exists(), "amplicon invalid run created output")
    return output_hash


def peak_arguments(case: dict[str, Any], paths: dict[str, Any], output: str, builds: list[str] | None = None) -> list[str]:
    config = case["arguments"]
    result = [
        "--contig-sizes", str(paths["contigs"]), "--contig-build", config["contig_build"],
        "--blacklist", str(paths["blacklist"]), "--blacklist-build", config["blacklist_build"],
        "--output", output,
    ]
    selected_builds = config["peak_builds"] if builds is None else builds
    for path, file_format, build in zip(paths["peaks"], config["peak_formats"], selected_builds):
        result.extend(["--peak", str(path), "--peak-format", file_format, "--peak-build", build])
    return result


def check_peaks(case: dict[str, Any], root: Path, checks: Checks) -> str:
    paths = {
        "contigs": materialize(case["contigs"], root, checks),
        "blacklist": materialize(case["blacklist"], root, checks),
        "peaks": [materialize(item, root, checks) for item in case["peaks"]],
    }
    first = run_cli(SCRIPTS["peak_qc"], peak_arguments(case, paths, "peaks-1.json"), root)
    second = run_cli(SCRIPTS["peak_qc"], peak_arguments(case, paths, "peaks-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "peak valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "peak completion differs")
    first_bytes = (root / "peaks-1.json").read_bytes()
    second_bytes = (root / "peaks-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "peak repeat bytes differ")
    output_hash = sha256_bytes(first_bytes)
    checks.require(output_hash == case["expected"]["output_sha256"], f"peak output hash differs: {output_hash}")
    report = strict_json_loads(first_bytes)
    checks.require(report["peak_sets"][0]["summary"]["duplicate_coordinate_count"] == case["expected"]["duplicate_coordinate_count"], "peak duplicate count differs")
    checks.require(report["pairwise_base_coverage"][0]["jaccard"] == case["expected"]["pairwise_jaccard"], "peak Jaccard differs")
    before = sha256_file(root / "peaks-1.json")
    overwrite = run_cli(SCRIPTS["peak_qc"], peak_arguments(case, paths, "peaks-1.json"), root)
    checks.require(overwrite.returncode != 0, "peak overwrite was accepted")
    checks.require(sha256_file(root / "peaks-1.json") == before, "peak overwrite changed output")
    rejected = run_cli(
        SCRIPTS["peak_qc"],
        peak_arguments(case, paths, "peaks-invalid.json", case["invalid"]["peak_builds"]),
        root,
    )
    checks.require(rejected.returncode == 2, "peak build mismatch was accepted")
    error = parse_event(rejected.stderr)
    checks.require(error.get("error", {}).get("code") == case["invalid"]["expected_error"], "peak invalid classification differs")
    checks.require(not (root / "peaks-invalid.json").exists(), "peak invalid run created output")
    return output_hash


def protein_arguments(case: dict[str, Any], matrix: Path, metadata: Path, output: str) -> list[str]:
    config = case["arguments"]
    return [
        "--matrix", matrix.name, "--metadata", metadata.name, "--output", output,
        "--protein-id-column", config["protein_id_column"],
        "--sample-id-column", config["sample_id_column"],
        "--condition-column", config["condition_column"],
        "--numerator", config["numerator"], "--denominator", config["denominator"],
        "--covariate-column", config["covariate_column"],
        "--declared-protein-level-normalized-log2",
    ]


def check_protein(case: dict[str, Any], root: Path, checks: Checks) -> str:
    matrix = materialize(case["matrix"], root, checks)
    metadata = materialize(case["metadata"], root, checks)
    invalid = materialize(case["invalid_matrix"], root, checks)
    first = run_cli(SCRIPTS["protein_da"], protein_arguments(case, matrix, metadata, "protein-1.json"), root)
    second = run_cli(SCRIPTS["protein_da"], protein_arguments(case, matrix, metadata, "protein-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, f"protein valid run failed: {first.stderr}")
    checks.require(parse_event(first.stdout).get("status") == "completed", "protein completion differs")
    first_bytes = (root / "protein-1.json").read_bytes()
    second_bytes = (root / "protein-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "protein repeat bytes differ")
    output_hash = sha256_bytes(first_bytes)
    checks.require(output_hash == case["expected"]["output_sha256"], f"protein output hash differs: {output_hash}")
    report = strict_json_loads(first_bytes)
    checks.require(len(report["results"]) == case["expected"]["protein_count"], "protein result count differs")
    checks.require(report["design"]["rank"] == case["expected"]["design_rank"], "protein design rank differs")
    checks.require(report["design"]["residual_degrees_of_freedom"] == case["expected"]["residual_degrees_of_freedom"], "protein residual degrees differ")
    checks.require(abs(report["results"][0]["effect_log2"] - case["expected"]["p1_effect_log2"]) < 1e-12, "protein effect oracle differs")
    before = sha256_file(root / "protein-1.json")
    overwrite = run_cli(SCRIPTS["protein_da"], protein_arguments(case, matrix, metadata, "protein-1.json"), root)
    checks.require(overwrite.returncode != 0, "protein overwrite was accepted")
    checks.require(sha256_file(root / "protein-1.json") == before, "protein overwrite changed output")
    rejected = run_cli(SCRIPTS["protein_da"], protein_arguments(case, invalid, metadata, "protein-invalid.json"), root)
    checks.require(rejected.returncode == 2, "protein nonfinite input was accepted")
    error = parse_event(rejected.stderr)
    checks.require(error.get("code") == case["invalid_matrix"]["expected_error"], "protein invalid classification differs")
    checks.require(not (root / "protein-invalid.json").exists(), "protein invalid run created output")
    return output_hash


def run_suite() -> dict[str, Any]:
    fixture = strict_json_loads(FIXTURE.read_bytes())
    if not isinstance(fixture, dict):
        raise RuntimeError("fixture is not an object")
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="bio02-wave-r2-minimal-") as temporary:
        root = Path(temporary)
        package_digests = check_package_bindings(fixture, checks)
        check_self_tests(fixture, root, checks)
        output_hashes = {
            "amplicon-feature-table-and-taxonomy-qc": check_amplicon(fixture["amplicon_qc"], root, checks),
            "chromatin-peak-set-qc": check_peaks(fixture["peak_qc"], root, checks),
            "protein-level-differential-abundance": check_protein(fixture["protein_da"], root, checks),
        }
    return {
        "checks": checks.count,
        "fixture_sha256": sha256_file(FIXTURE),
        "network_performed": False,
        "output_sha256": output_hashes,
        "package_digests": package_digests,
        "status": "pass",
        "suite_version": VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--version", action="version", version=VERSION)
    command.parse_args(argv)
    try:
        print(json.dumps(run_suite(), sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "status": "failed"}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
