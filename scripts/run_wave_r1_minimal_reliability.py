#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay retained, offline minimum-reliability checks for Wave R1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

from validate_skeleton import package_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "research-wave-r1-minimal-v0.3.json"
VERSION = "0.3.0"
PACKAGE_NAMES = (
    "missing-data-and-sensitivity-analysis",
    "protein-interface-contact-analysis",
    "public-orthology-retrieval-and-qc",
)
MISSING_SCRIPT = ROOT / "skills" / PACKAGE_NAMES[0] / "scripts" / "analyze_missing_outcomes.py"
CONTACT_SCRIPT = ROOT / "skills" / PACKAGE_NAMES[1] / "scripts" / "analyze_contacts.py"
CONNECTOR_SCRIPT = ROOT / "scripts" / "run_research_connector.py"


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(message)
        self.count += 1


def strict_json_loads(payload: str | bytes) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(
        payload,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(script: Path, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
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


def materialize(case: dict[str, Any], directory: Path, checks: Checks) -> tuple[Path, bytes]:
    payload = case["content"].encode("utf-8")
    checks.require(sha256_bytes(payload) == case["sha256"], f"fixture hash differs: {case['filename']}")
    path = directory / case["filename"]
    path.write_bytes(payload)
    checks.require(path.read_bytes() == payload, f"fixture materialization differs: {case['filename']}")
    return path, payload


def missing_arguments(config: dict[str, str], input_path: Path, output: str) -> list[str]:
    return [
        "--input", str(input_path), "--output", output,
        "--outcome-column", config["outcome_column"],
        "--group-column", config["group_column"],
        "--lower-bound", config["lower_bound"],
        "--upper-bound", config["upper_bound"],
        f"--delta-grid={config['delta_grid']}",
        "--missing-token", config["missing_token"],
        "--delimiter", "csv",
    ]


def check_missing(suite: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    config = suite["arguments"]
    valid_path, _ = materialize(suite["valid"], root, checks)
    first = run_cli(MISSING_SCRIPT, missing_arguments(config, valid_path, "missing-1.json"), root)
    second = run_cli(MISSING_SCRIPT, missing_arguments(config, valid_path, "missing-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "missing-data valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "missing-data status differs")
    first_bytes = (root / "missing-1.json").read_bytes()
    second_bytes = (root / "missing-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "missing-data repeat bytes differ")
    valid_hash = sha256_bytes(first_bytes)
    checks.require(
        valid_hash == suite["valid"]["output_sha256"],
        f"missing-data output hash differs: {valid_hash}",
    )
    report = strict_json_loads(first_bytes)
    checks.require(report["overall"]["total_rows"] == suite["valid"]["expected_total_rows"], "missing-data row count differs")
    checks.require(report["overall"]["missing_rows"] == suite["valid"]["expected_missing_rows"], "missing-data missing count differs")

    before = sha256_file(root / "missing-1.json")
    overwrite = run_cli(MISSING_SCRIPT, missing_arguments(config, valid_path, "missing-1.json"), root)
    checks.require(overwrite.returncode != 0, "missing-data overwrite was accepted")
    checks.require(sha256_file(root / "missing-1.json") == before, "missing-data overwrite changed output")

    empty_path, _ = materialize(suite["empty"], root, checks)
    empty = run_cli(MISSING_SCRIPT, missing_arguments(config, empty_path, "missing-empty.json"), root)
    checks.require(empty.returncode == 0, "missing-data all-missing case failed")
    empty_report = strict_json_loads((root / "missing-empty.json").read_bytes())
    checks.require(empty_report["overall"]["total_rows"] == suite["empty"]["expected_total_rows"], "missing-data empty row count differs")
    checks.require(empty_report["overall"]["observed_rows"] == suite["empty"]["expected_observed_rows"], "missing-data empty observed count differs")
    checks.require(empty_report["overall"]["complete_case_mean"] is None, "missing-data empty result was estimated")

    malformed_path, _ = materialize(suite["malformed"], root, checks)
    malformed = run_cli(MISSING_SCRIPT, missing_arguments(config, malformed_path, "missing-malformed.json"), root)
    checks.require(malformed.returncode == 2, "missing-data malformed case was not rejected")
    error = parse_event(malformed.stderr)
    codes = [item.get("code") for item in error.get("issues", [])]
    checks.require(error.get("status") == "invalid-input" and suite["malformed"]["expected_issue"] in codes, "missing-data malformed classification differs")
    checks.require(not (root / "missing-malformed.json").exists(), "missing-data malformed case created output")
    return {"valid_output": valid_hash}


def contact_arguments(config: dict[str, str], input_path: Path, output: str) -> list[str]:
    return [
        "--input", str(input_path), "--chain-a", config["chain_a"],
        "--chain-b", config["chain_b"], "--cutoff", config["cutoff"],
        "--output", output,
    ]


def check_contacts(suite: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    config = suite["arguments"]
    valid_path, _ = materialize(suite["valid"], root, checks)
    first = run_cli(CONTACT_SCRIPT, contact_arguments(config, valid_path, "contacts-1.json"), root)
    second = run_cli(CONTACT_SCRIPT, contact_arguments(config, valid_path, "contacts-2.json"), root)
    checks.require(first.returncode == second.returncode == 0, "contact valid run failed")
    checks.require(parse_event(first.stdout).get("status") == "completed", "contact status differs")
    first_bytes = (root / "contacts-1.json").read_bytes()
    second_bytes = (root / "contacts-2.json").read_bytes()
    checks.require(first_bytes == second_bytes, "contact repeat bytes differ")
    valid_hash = sha256_bytes(first_bytes)
    checks.require(
        valid_hash == suite["valid"]["output_sha256"],
        f"contact output hash differs: {valid_hash}",
    )
    report = strict_json_loads(first_bytes)
    checks.require(report["summary"]["contact_count"] == suite["valid"]["expected_contact_count"], "contact count differs")
    checks.require(report["contacts"][0]["minimum_distance_angstrom"] == suite["valid"]["expected_distance_angstrom"], "contact distance differs")

    before = sha256_file(root / "contacts-1.json")
    overwrite = run_cli(CONTACT_SCRIPT, contact_arguments(config, valid_path, "contacts-1.json"), root)
    checks.require(overwrite.returncode == 2, "contact overwrite was accepted")
    checks.require(sha256_file(root / "contacts-1.json") == before, "contact overwrite changed output")

    empty_path, _ = materialize(suite["empty"], root, checks)
    empty = run_cli(CONTACT_SCRIPT, contact_arguments(config, empty_path, "contacts-empty.json"), root)
    checks.require(empty.returncode == 0, "contact empty case failed")
    empty_report = strict_json_loads((root / "contacts-empty.json").read_bytes())
    checks.require(empty_report["summary"]["contact_count"] == suite["empty"]["expected_contact_count"], "contact empty classification differs")
    checks.require(empty_report["contacts"] == [], "contact empty result contains contacts")

    malformed_path, _ = materialize(suite["malformed"], root, checks)
    malformed = run_cli(CONTACT_SCRIPT, contact_arguments(config, malformed_path, "contacts-malformed.json"), root)
    checks.require(malformed.returncode == 2, "contact malformed case was not rejected")
    error = parse_event(malformed.stderr)
    checks.require(error.get("error", {}).get("code") == suite["malformed"]["expected_error"], "contact malformed classification differs")
    checks.require(not (root / "contacts-malformed.json").exists(), "contact malformed case created output")
    return {"valid_output": valid_hash}


def classify_orthology(payload: bytes, request: dict[str, str]) -> str:
    try:
        document = strict_json_loads(payload)
    except (UnicodeError, json.JSONDecodeError):
        return "invalid"
    if not isinstance(document, dict) or not isinstance(document.get("data"), list):
        return "invalid"
    data = document["data"]
    if len(data) != 1 or not isinstance(data[0], dict) or data[0].get("id") != request["source_id"]:
        return "invalid"
    homologies = data[0].get("homologies")
    if not isinstance(homologies, list):
        return "invalid"
    if not homologies:
        return "no-ortholog-returned"
    for item in homologies:
        if (
            not isinstance(item, dict)
            or item.get("id") != request["target_id"]
            or item.get("species") != request["target_species"]
            or not isinstance(item.get("type"), str)
        ):
            return "invalid"
    return "completed"


def connector_args(request: dict[str, str], output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        self_test=False, provider="ensembl-rest", url=request["url"], output=output,
        provenance=None, method="GET", pages=1, page_param=None, page_start=1,
        page_step=1, max_bytes=1024 * 1024, timeout=1, retries=0,
        acknowledge_terms=False,
    )


def check_orthology(suite: dict[str, Any], root: Path, checks: Checks) -> dict[str, str | bool]:
    connector = load_module(CONNECTOR_SCRIPT, "wave_r1_research_connector")
    catalog = connector.load_catalog()
    request = suite["request"]
    connector._NETWORK_PERFORMED = False
    call_count = 0

    def execute_case(case_name: str, output_name: str) -> tuple[dict[str, Any], bytes]:
        nonlocal call_count
        case = suite[case_name]
        body = case["content"].encode("utf-8")
        checks.require(sha256_bytes(body) == case["sha256"], f"fixture hash differs: {case['filename']}")

        def fake_open(request_object: Any, _timeout: float) -> Any:
            nonlocal call_count
            call_count += 1
            checks.require(request_object.full_url == request["url"], "orthology request URL differs")
            return connector.FakeResponse(request_object.full_url, body)

        args = connector_args(request, root / output_name)
        connector.validate_args(args)
        event = connector.execute(args, catalog, open_request=fake_open, sleeper=lambda _seconds: None)
        output = root / output_name
        provenance_path = output.with_name(f"{output.name}.provenance.json")
        output_bytes = output.read_bytes()
        provenance = strict_json_loads(provenance_path.read_bytes())
        checks.require(provenance.get("provider_id") == "ensembl-rest", "orthology provenance provider differs")
        checks.require(provenance.get("request_urls") == [request["url"]], "orthology provenance URL differs")
        checks.require(provenance.get("sha256") == sha256_bytes(output_bytes), "orthology provenance hash differs")
        checks.require(provenance.get("output_file") == output.name, "orthology provenance output name differs")
        return event, output_bytes

    first_event, first_bytes = execute_case("valid", "orthology-1.json")
    second_event, second_bytes = execute_case("valid", "orthology-2.json")
    checks.require(first_event["status"] == second_event["status"] == "completed", "orthology valid retrieval failed")
    checks.require(first_bytes == second_bytes, "orthology repeat bytes differ")
    checks.require(classify_orthology(first_bytes, request) == suite["valid"]["expected_classification"], "orthology valid classification differs")
    checks.require(sha256_bytes(first_bytes) == suite["valid"]["sha256"], "orthology valid output hash differs")

    before_calls = call_count
    before_hash = sha256_file(root / "orthology-1.json")
    provenance_path = root / "orthology-1.json.provenance.json"
    before_provenance_hash = sha256_file(provenance_path)
    try:
        execute_case("valid", "orthology-1.json")
    except connector.ConnectorError:
        pass
    else:
        raise RuntimeError("orthology overwrite was accepted")
    checks.require(call_count == before_calls, "orthology overwrite reached fake transport")
    checks.require(sha256_file(root / "orthology-1.json") == before_hash, "orthology overwrite changed output")
    checks.require(sha256_file(provenance_path) == before_provenance_hash, "orthology overwrite changed provenance")

    empty_event, empty_bytes = execute_case("empty", "orthology-empty.json")
    checks.require(empty_event["status"] == "completed", "orthology empty retrieval failed")
    checks.require(classify_orthology(empty_bytes, request) == suite["empty"]["expected_classification"], "orthology empty classification differs")

    malformed = suite["malformed"]
    malformed_body = malformed["content"].encode("utf-8")
    checks.require(sha256_bytes(malformed_body) == malformed["sha256"], "orthology malformed fixture hash differs")

    def fake_malformed(request_object: Any, _timeout: float) -> Any:
        nonlocal call_count
        call_count += 1
        return connector.FakeResponse(request_object.full_url, malformed_body)

    malformed_output = root / "orthology-malformed.json"
    try:
        connector.execute(
            connector_args(request, malformed_output), catalog,
            open_request=fake_malformed, sleeper=lambda _seconds: None,
        )
    except connector.ConnectorError:
        pass
    else:
        raise RuntimeError("orthology malformed response was accepted")
    checks.require(classify_orthology(malformed_body, request) == malformed["expected_classification"], "orthology malformed classification differs")
    checks.require(not malformed_output.exists(), "orthology malformed response created payload")
    checks.require(not malformed_output.with_name(f"{malformed_output.name}.provenance.json").exists(), "orthology malformed response created provenance")
    checks.require(call_count == 4, "orthology fake transport call count differs")
    checks.require(connector._NETWORK_PERFORMED is False, "orthology test performed live network access")
    return {
        "network_performed": False,
        "transport_simulated": True,
        "valid_output": sha256_bytes(first_bytes),
    }


def run() -> dict[str, Any]:
    checks = Checks()
    for invalid_json in ('{"key":1,"key":2}', '{"key":NaN}'):
        try:
            strict_json_loads(invalid_json)
        except ValueError:
            rejected = True
        else:
            rejected = False
        checks.require(rejected, "non-canonical JSON was accepted")
    fixture = strict_json_loads(FIXTURE.read_bytes())
    checks.require(fixture.get("schema_version") == "0.1.0", "fixture schema differs")
    checks.require(fixture.get("suite_version") == VERSION, "fixture suite version differs")
    checks.require(fixture.get("scope", {}).get("offline") is True, "fixture is not offline")
    checks.require(fixture.get("scope", {}).get("formal_scientific_evaluation") is False, "fixture overclaims evaluation")

    registry = strict_json_loads((ROOT / "registry.json").read_bytes())
    declared = {item["name"]: item["package_digest"] for item in registry["skills"]}
    package_hashes = {name: package_digest(ROOT / "skills" / name) for name in PACKAGE_NAMES}
    for name, digest in package_hashes.items():
        checks.require(digest == declared.get(name), f"package digest differs: {name}")

    with tempfile.TemporaryDirectory(prefix="wave-r1-minimal-") as temporary:
        temporary_root = Path(temporary)
        result_hashes = {
            "missing_data": check_missing(fixture["missing_data"], temporary_root, checks),
            "protein_contacts": check_contacts(fixture["protein_contacts"], temporary_root, checks),
            "orthology": check_orthology(fixture["orthology"], temporary_root, checks),
        }

    return {
        "checks": checks.count,
        "hashes": {
            "packages": package_hashes,
            "scripts": {
                "missing_data": sha256_file(MISSING_SCRIPT),
                "protein_contacts": sha256_file(CONTACT_SCRIPT),
                "research_connector": sha256_file(CONNECTOR_SCRIPT),
                "runner": sha256_file(Path(__file__)),
            },
            "fixture": sha256_file(FIXTURE),
            "outputs": result_hashes,
        },
        "network_performed": False,
        "status": "pass",
        "version": VERSION,
    }


def main() -> int:
    checks = 0
    try:
        result = run()
        checks = int(result["checks"])
    except Exception as exc:
        print(json.dumps({"checks": checks, "reason": str(exc), "status": "fail", "version": VERSION}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
