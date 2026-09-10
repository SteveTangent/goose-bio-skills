#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay retained offline minimum-reliability checks for Wave R5."""

from __future__ import annotations

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
FIXTURE = ROOT / "evals/fixtures/research-wave-r5-minimal-v0.3.json"
VERSION = "0.3.0"
PACKAGES = {
    "matrix": "bulk-rnaseq-gene-count-matrix-assembly",
    "beta": "amplicon-beta-diversity-distance-analysis",
    "logrank": "two-group-log-rank-survival-comparison",
    "arcsinh": "flow-cytometry-arcsinh-transformation",
}
SCRIPTS = {
    "matrix": ROOT / "skills" / PACKAGES["matrix"] / "scripts/assemble_gene_count_matrix.py",
    "beta": ROOT / "skills" / PACKAGES["beta"] / "scripts/calculate_beta_distances.py",
    "logrank": ROOT / "skills" / PACKAGES["logrank"] / "scripts/compare_log_rank.py",
    "arcsinh": ROOT / "skills" / PACKAGES["arcsinh"] / "scripts/apply_arcsinh.py",
}


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(message)
        self.count += 1


def strict_json(payload: bytes | str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(payload, object_pairs_hook=reject_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"non-standard constant: {value}")))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_cli(script: Path, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments], cwd=cwd,
        env={
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        },
        text=True, capture_output=True, timeout=45, check=False,
    )


def one_event(text: str) -> dict[str, Any]:
    lines = text.strip().splitlines()
    if len(lines) != 1:
        raise RuntimeError("helper did not emit exactly one JSON event")
    event = strict_json(lines[0])
    if not isinstance(event, dict):
        raise RuntimeError("helper event is not an object")
    return event


def materialize(case: dict[str, Any], field: str, name: str,
                directory: Path, checks: Checks) -> Path:
    payload = case[field].encode()
    checks.require(sha256_bytes(payload) == case["input_sha256"][field],
                   f"{field} fixture hash differs")
    path = directory / name
    path.write_bytes(payload)
    checks.require(path.read_bytes() == payload, f"{field} materialization differs")
    return path


def valid_twice(root: Path, key: str, case: dict[str, Any],
                inputs: list[tuple[str, str]], arguments: list[str],
                outputs: list[str], checks: Checks) -> tuple[list[bytes], str, Path]:
    run_outputs: list[list[bytes]] = []
    events: list[str] = []
    first_root: Path | None = None
    for number in (1, 2):
        run_root = root / f"{key}-{number}"
        run_root.mkdir()
        if first_root is None:
            first_root = run_root
        for field, name in inputs:
            materialize(case, field, name, run_root, checks)
        result = run_cli(SCRIPTS[key], arguments, run_root)
        checks.require(result.returncode == 0, f"{key} valid run failed: {result.stderr}")
        checks.require(one_event(result.stdout).get("status") == "completed",
                       f"{key} completion status differs")
        events.append(result.stdout)
        run_outputs.append([(run_root / name).read_bytes() for name in outputs])
    checks.require(run_outputs[0] == run_outputs[1], f"{key} output bytes differ")
    checks.require(events[0] == events[1], f"{key} event lines differ")
    assert first_root is not None
    return run_outputs[0], events[0], first_root


def bind_packages(fixture: dict[str, Any], checks: Checks) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for key, name in PACKAGES.items():
        digest = package_digest(ROOT / "skills" / name)
        checks.require(digest == fixture[key]["package_digest"],
                       f"{name} package digest differs")
        bindings[name] = digest
    return bindings


def check_self_tests(fixture: dict[str, Any], root: Path, checks: Checks) -> None:
    for key, script in SCRIPTS.items():
        result = run_cli(script, ["--self-test"], root)
        checks.require(result.returncode == 0, f"{key} self-test failed")
        checks.require(one_event(result.stdout) == fixture[key]["self_test"],
                       f"{key} self-test event differs")


def check_matrix(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    args = ["--count-json", "b.json", "a.json", "--output", "out.json"]
    outputs, _, first = valid_twice(
        root, "matrix", case, [("a", "a.json"), ("b", "b.json")],
        args, ["out.json"], checks,
    )
    report = strict_json(outputs[0])
    checks.require(report["matrix"]["sample_ids"] == ["sample-a", "sample-b"],
                   "matrix sample order differs")
    checks.require([row["gene_id"] for row in report["matrix"]["genes"]] == ["gA", "gB"],
                   "matrix gene order differs")
    checks.require(report["matrix"]["genes"][0]["counts"] == [2, 0],
                   "matrix gA counts differ")
    checks.require(report["matrix"]["genes"][1]["counts"] == [1, 3],
                   "matrix gB counts differ")
    digest = sha256_bytes(outputs[0])
    checks.require(digest == case["output_sha256"], "matrix output hash differs")
    before = sha256_file(first / "out.json")
    overwrite = run_cli(SCRIPTS["matrix"], args, first)
    checks.require(overwrite.returncode != 0, "matrix overwrite accepted")
    checks.require(sha256_file(first / "out.json") == before, "matrix overwrite changed output")
    invalid = root / "matrix-invalid"; invalid.mkdir()
    materialize(case, "a", "a.json", invalid, checks)
    materialize(case, "invalid_b", "b.json", invalid, checks)
    failed = run_cli(SCRIPTS["matrix"], args, invalid)
    checks.require(failed.returncode == 2, "matrix mismatch accepted")
    checks.require(one_event(failed.stderr).get("code") == "gtf-fingerprint-mismatch",
                   "matrix invalid classification differs")
    checks.require(not (invalid / "out.json").exists(), "matrix invalid output exists")
    return {"report": digest}


def check_beta(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    args = ["--feature-table", "table.tsv", "--output", "out.json"]
    outputs, _, first = valid_twice(
        root, "beta", case, [("table", "table.tsv")], args, ["out.json"], checks,
    )
    report = strict_json(outputs[0]); pairs = {
        (row["sample_a"], row["sample_b"]): row for row in report["pairs"]
    }
    checks.require(report["sample_ids"] == ["A", "B", "C", "Z"], "beta order differs")
    checks.require(pairs[("A", "B")]["bray_curtis"]["numerator"] == 1 and
                   pairs[("A", "B")]["bray_curtis"]["denominator"] == 3,
                   "beta A-B Bray-Curtis differs")
    checks.require(pairs[("B", "C")]["jaccard_presence_absence"]["numerator"] == 2 and
                   pairs[("B", "C")]["jaccard_presence_absence"]["denominator"] == 2,
                   "beta B-C Jaccard differs")
    checks.require(all(pairs[(sample, "Z")]["bray_curtis"]["status"] == "not-estimable"
                       for sample in ("A", "B", "C")), "beta zero-depth boundary differs")
    digest = sha256_bytes(outputs[0])
    checks.require(digest == case["output_sha256"], "beta output hash differs")
    before = sha256_file(first / "out.json")
    overwrite = run_cli(SCRIPTS["beta"], args, first)
    checks.require(overwrite.returncode != 0, "beta overwrite accepted")
    checks.require(sha256_file(first / "out.json") == before, "beta overwrite changed output")
    invalid = root / "beta-invalid"; invalid.mkdir()
    materialize(case, "invalid", "table.tsv", invalid, checks)
    failed = run_cli(SCRIPTS["beta"], args, invalid)
    checks.require(failed.returncode == 2, "beta negative count accepted")
    checks.require(one_event(failed.stderr).get("status") == "invalid-input",
                   "beta invalid status differs")
    checks.require(not (invalid / "out.json").exists(), "beta invalid output exists")
    return {"report": digest}


def check_logrank(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    args = ["--input", "subjects.tsv", "--output", "out.json"]
    outputs, _, first = valid_twice(
        root, "logrank", case, [("table", "subjects.tsv")], args, ["out.json"], checks,
    )
    report = strict_json(outputs[0]); totals = report["totals"]
    checks.require(totals["observed_events"]["group_a"] == 2, "logrank observed differs")
    checks.require(totals["expected_events"]["group_a"]["numerator"] == 13 and
                   totals["expected_events"]["group_a"]["denominator"] == 10,
                   "logrank expectation differs")
    checks.require(totals["variance_group_a"]["numerator"] == 61 and
                   totals["variance_group_a"]["denominator"] == 100,
                   "logrank variance differs")
    checks.require(report["comparison"]["chi_square"]["numerator"] == 49 and
                   report["comparison"]["chi_square"]["denominator"] == 61,
                   "logrank chi-square differs")
    checks.require(report["analysis"]["decisions_or_thresholds_applied"] is False,
                   "logrank emitted a decision")
    digest = sha256_bytes(outputs[0])
    checks.require(digest == case["output_sha256"], "logrank output hash differs")
    before = sha256_file(first / "out.json")
    overwrite = run_cli(SCRIPTS["logrank"], args, first)
    checks.require(overwrite.returncode != 0, "logrank overwrite accepted")
    checks.require(sha256_file(first / "out.json") == before, "logrank overwrite changed output")
    invalid = root / "logrank-invalid"; invalid.mkdir()
    materialize(case, "invalid", "subjects.tsv", invalid, checks)
    failed = run_cli(SCRIPTS["logrank"], args, invalid)
    checks.require(failed.returncode == 2, "logrank invalid event accepted")
    checks.require(one_event(failed.stderr).get("status") == "invalid-input",
                   "logrank invalid status differs")
    checks.require(not (invalid / "out.json").exists(), "logrank invalid output exists")
    return {"report": digest}


def check_arcsinh(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    args = ["--events", "events.tsv", "--cofactors", "cofactors.tsv",
            "--output-events", "out.tsv", "--output-report", "out.json"]
    outputs, _, first = valid_twice(
        root, "arcsinh", case, [("events", "events.tsv"), ("cofactors", "cofactors.tsv")],
        args, ["out.tsv", "out.json"], checks,
    )
    rows = outputs[0].decode().splitlines()
    checks.require(rows[1].split("\t")[1:] ==
                   ["0.881373587019543", "-0.48121182505960347", "7.00"],
                   "arcsinh first row differs")
    checks.require(rows[2].split("\t")[1:] == ["0", "0.881373587019543", "8e0"],
                   "arcsinh zero or unselected token differs")
    report = strict_json(outputs[1])
    checks.require(report["transformation"]["formula"] == "asinh(value/cofactor)",
                   "arcsinh formula differs")
    digests = {"events": sha256_bytes(outputs[0]), "report": sha256_bytes(outputs[1])}
    checks.require(digests == case["output_sha256"], "arcsinh output hashes differ")
    before = [sha256_file(first / name) for name in ("out.tsv", "out.json")]
    overwrite = run_cli(SCRIPTS["arcsinh"], args, first)
    checks.require(overwrite.returncode != 0, "arcsinh overwrite accepted")
    checks.require(before == [sha256_file(first / name) for name in ("out.tsv", "out.json")],
                   "arcsinh overwrite changed output")
    invalid = root / "arcsinh-invalid"; invalid.mkdir()
    materialize(case, "events", "events.tsv", invalid, checks)
    materialize(case, "invalid_cofactors", "cofactors.tsv", invalid, checks)
    failed = run_cli(SCRIPTS["arcsinh"], args, invalid)
    checks.require(failed.returncode == 2, "arcsinh nonpositive cofactor accepted")
    event = one_event(failed.stderr)
    checks.require(event.get("code") == "nonpositive-cofactor" and
                   event.get("status") == "needs-decision",
                   "arcsinh invalid classification differs")
    checks.require(not (invalid / "out.tsv").exists() and not (invalid / "out.json").exists(),
                   "arcsinh invalid outputs exist")
    return digests


def main() -> int:
    fixture = strict_json(FIXTURE.read_bytes())
    if not isinstance(fixture, dict):
        raise ValueError("fixture root is not an object")
    checks = Checks()
    bindings = bind_packages(fixture, checks)
    with tempfile.TemporaryDirectory(prefix="bio02-wave-r5-minimum-") as temporary:
        root = Path(temporary)
        check_self_tests(fixture, root, checks)
        output_hashes = {
            PACKAGES["matrix"]: check_matrix(fixture["matrix"], root, checks),
            PACKAGES["beta"]: check_beta(fixture["beta"], root, checks),
            PACKAGES["logrank"]: check_logrank(fixture["logrank"], root, checks),
            PACKAGES["arcsinh"]: check_arcsinh(fixture["arcsinh"], root, checks),
        }
    print(json.dumps({
        "checks": checks.count,
        "fixture_sha256": sha256_file(FIXTURE),
        "network_performed": False,
        "output_sha256": output_hashes,
        "package_digests": bindings,
        "status": "pass",
        "version": VERSION,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "status": "fail", "version": VERSION},
                         sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
