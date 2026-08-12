#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay retained, offline minimum-reliability checks for Wave R4."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "research-wave-r4-minimal-v0.1.json"
VERSION = "0.1.0"
PACKAGES = {
    "bulk_gene_counting": "bulk-rnaseq-gene-counting-from-alignment",
    "junction_psi": "junction-psi-and-delta-analysis",
    "alpha_diversity": "amplicon-alpha-diversity-analysis",
    "flow_compensation": "flow-cytometry-compensation-application",
    "kaplan_meier": "kaplan-meier-survival-analysis",
    "clinvar_evidence": "human-variant-evidence-retrieval",
}
SCRIPTS = {
    "bulk_gene_counting": ROOT / "skills" / PACKAGES["bulk_gene_counting"] / "scripts" / "count_gene_alignments.py",
    "junction_psi": ROOT / "skills" / PACKAGES["junction_psi"] / "scripts" / "calculate_junction_psi.py",
    "alpha_diversity": ROOT / "skills" / PACKAGES["alpha_diversity"] / "scripts" / "calculate_alpha_diversity.py",
    "flow_compensation": ROOT / "skills" / PACKAGES["flow_compensation"] / "scripts" / "apply_compensation.py",
    "kaplan_meier": ROOT / "skills" / PACKAGES["kaplan_meier"] / "scripts" / "analyze_kaplan_meier.py",
    "clinvar_evidence": ROOT / "skills" / PACKAGES["clinvar_evidence"] / "scripts" / "normalize_clinvar_vcv.py",
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


def run_cli(script: Path, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = {
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
        timeout=45,
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


def materialize(
    case: dict[str, Any], field: str, filename: str, directory: Path, checks: Checks
) -> Path:
    payload = case[field].encode("utf-8")
    expected = case["input_sha256"][field]
    checks.require(sha256_bytes(payload) == expected, f"fixture hash differs: {field}")
    path = directory / filename
    path.write_bytes(payload)
    checks.require(path.read_bytes() == payload, f"fixture materialization differs: {field}")
    return path


def new_run_root(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir()
    return path


def run_twice(
    root: Path,
    prefix: str,
    setup: Callable[[Path], list[str]],
    script: Path,
    outputs: tuple[str, ...],
    checks: Checks,
) -> tuple[list[bytes], Path, list[str]]:
    all_bytes: list[list[bytes]] = []
    events: list[dict[str, Any]] = []
    roots: list[Path] = []
    for index in (1, 2):
        run_root = new_run_root(root, f"{prefix}-{index}")
        roots.append(run_root)
        arguments = setup(run_root)
        completed = run_cli(script, arguments, run_root)
        checks.require(completed.returncode == 0, f"{prefix} valid run failed: {completed.stderr}")
        event = parse_event(completed.stdout)
        checks.require(event.get("status") in {"completed", "partial"}, f"{prefix} status differs")
        events.append(event)
        all_bytes.append([(run_root / name).read_bytes() for name in outputs])
    checks.require(all_bytes[0] == all_bytes[1], f"{prefix} repeat bytes differ")
    return all_bytes[0], roots[0], setup(roots[0])


def check_self_tests(fixture: dict[str, Any], root: Path, checks: Checks) -> None:
    for key, script in SCRIPTS.items():
        completed = run_cli(script, ["--self-test"], root)
        checks.require(completed.returncode == 0, f"{key} self-test failed: {completed.stderr}")
        checks.require(parse_event(completed.stdout) == fixture[key]["self_test"], f"{key} self-test event differs")


def check_package_bindings(fixture: dict[str, Any], checks: Checks) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, name in PACKAGES.items():
        digest = package_digest(ROOT / "skills" / name)
        checks.require(digest == fixture[key]["package_digest"], f"{name} package digest differs")
        result[name] = digest
    return result


def check_bulk(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        materialize(case, "sam", "sample.sam", run_root, checks)
        materialize(case, "gtf", "genes.gtf", run_root, checks)
        return [
            "--sam", "sample.sam", "--gtf", "genes.gtf", "--sample-id", "sample1",
            "--strandedness", "unstranded", "--min-mapq", "20", "--output", "counts.json",
        ]

    outputs, first_root, arguments = run_twice(
        root, "bulk", setup, SCRIPTS["bulk_gene_counting"], ("counts.json",), checks
    )
    report = strict_json_loads(outputs[0])
    expected = case["expected"]
    counts = {row["gene_id"]: row["count"] for row in report["counts"]}
    checks.require(counts == {"geneA": expected["geneA"], "geneB": expected["geneB"]}, "bulk gene counts differ")
    for key in ("assigned", "ambiguous", "no_feature", "low_mapq", "unmapped", "multimapped"):
        checks.require(report["assignment_summary"][key] == expected[key], f"bulk {key} differs")
    output_hash = sha256_bytes(outputs[0])
    checks.require(output_hash == case["output_sha256"], "bulk output hash differs")
    before = sha256_file(first_root / "counts.json")
    overwrite = run_cli(SCRIPTS["bulk_gene_counting"], arguments, first_root)
    checks.require(overwrite.returncode != 0, "bulk overwrite was accepted")
    checks.require(sha256_file(first_root / "counts.json") == before, "bulk overwrite changed output")
    invalid_root = new_run_root(root, "bulk-invalid")
    invalid_arguments = setup(invalid_root)
    invalid_arguments[invalid_arguments.index("20")] = "256"
    invalid = run_cli(SCRIPTS["bulk_gene_counting"], invalid_arguments, invalid_root)
    checks.require(invalid.returncode == 2, "bulk invalid MAPQ was accepted")
    checks.require(parse_event(invalid.stderr).get("status") == "invalid-input", "bulk invalid status differs")
    checks.require(not (invalid_root / "counts.json").exists(), "bulk invalid run created output")
    return {"report": output_hash}


def check_junction(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        materialize(case, "counts", "counts.tsv", run_root, checks)
        materialize(case, "groups", "groups.tsv", run_root, checks)
        return [
            "--counts", "counts.tsv", "--groups", "groups.tsv", "--group-a", "control",
            "--group-b", "treated", "--min-coverage", "10", "--output", "psi.json",
        ]

    outputs, first_root, arguments = run_twice(
        root, "junction", setup, SCRIPTS["junction_psi"], ("psi.json",), checks
    )
    report = strict_json_loads(outputs[0])
    expected = case["expected"]
    for key in ("events", "samples", "event_sample_pairs", "estimable_event_sample_pairs"):
        checks.require(report["summary"][key] == expected[key], f"junction {key} differs")
    checks.require(report["events"][0]["delta"]["contrast"] == "treated - control", "junction contrast differs")
    checks.require(report["events"][0]["delta"]["delta_psi_fraction"] == "2/5", "junction E1 delta differs")
    output_hash = sha256_bytes(outputs[0])
    checks.require(output_hash == case["output_sha256"], "junction output hash differs")
    before = sha256_file(first_root / "psi.json")
    overwrite = run_cli(SCRIPTS["junction_psi"], arguments, first_root)
    checks.require(overwrite.returncode == 2, "junction overwrite was accepted")
    checks.require(sha256_file(first_root / "psi.json") == before, "junction overwrite changed output")
    invalid_root = new_run_root(root, "junction-invalid")
    invalid_arguments = setup(invalid_root)
    invalid_arguments[invalid_arguments.index("10")] = "0"
    invalid = run_cli(SCRIPTS["junction_psi"], invalid_arguments, invalid_root)
    checks.require(invalid.returncode == 2, "junction invalid coverage was accepted")
    checks.require("[invalid-minimum-coverage]" in invalid.stderr, "junction invalid classification differs")
    checks.require(not (invalid_root / "psi.json").exists(), "junction invalid run created output")
    return {"report": output_hash}


def check_alpha(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        materialize(case, "table", "features.tsv", run_root, checks)
        return ["--feature-table", "features.tsv", "--output", "alpha.json"]

    outputs, first_root, arguments = run_twice(
        root, "alpha", setup, SCRIPTS["alpha_diversity"], ("alpha.json",), checks
    )
    report = strict_json_loads(outputs[0])
    expected = case["expected"]
    samples = {item["sample_id"]: item for item in report["samples"]}
    checks.require(samples["S1"]["depth"] == expected["S1_depth"], "alpha depth differs")
    checks.require(samples["S1"]["observed_features"]["value"] == expected["S1_observed"], "alpha observed differs")
    checks.require(samples["S1"]["shannon_natural_log"]["value"] == expected["S1_shannon"], "alpha Shannon differs")
    checks.require(samples["S1"]["simpson_one_minus_sum_squared"]["value"] == expected["S1_simpson"], "alpha Simpson differs")
    checks.require(samples["S3"]["observed_features"]["status"] == expected["S3_status"], "alpha zero-depth status differs")
    output_hash = sha256_bytes(outputs[0])
    checks.require(output_hash == case["output_sha256"], "alpha output hash differs")
    before = sha256_file(first_root / "alpha.json")
    overwrite = run_cli(SCRIPTS["alpha_diversity"], arguments, first_root)
    checks.require(overwrite.returncode != 0, "alpha overwrite was accepted")
    checks.require(sha256_file(first_root / "alpha.json") == before, "alpha overwrite changed output")
    invalid_root = new_run_root(root, "alpha-invalid")
    materialize(case, "invalid_table", "invalid.tsv", invalid_root, checks)
    invalid = run_cli(SCRIPTS["alpha_diversity"], ["--feature-table", "invalid.tsv", "--output", "invalid.json"], invalid_root)
    checks.require(invalid.returncode == 2, "alpha negative count was accepted")
    checks.require(parse_event(invalid.stderr).get("status") == "invalid-input", "alpha invalid status differs")
    checks.require(not (invalid_root / "invalid.json").exists(), "alpha invalid run created output")
    return {"report": output_hash}


def check_flow(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        materialize(case, "events", "events.tsv", run_root, checks)
        materialize(case, "spillover", "spillover.tsv", run_root, checks)
        return [
            "--events", "events.tsv", "--spillover", "spillover.tsv",
            "--output-events", "compensated.tsv", "--output-report", "report.json",
        ]

    outputs, first_root, arguments = run_twice(
        root, "flow", setup, SCRIPTS["flow_compensation"], ("compensated.tsv", "report.json"), checks
    )
    report = strict_json_loads(outputs[1])
    expected = case["expected"]
    checks.require(report["dimensions"] == {"channel_count": expected["channels"], "event_count": expected["events"]}, "flow dimensions differ")
    rows = list(csv.reader(io.StringIO(outputs[0].decode("utf-8")), delimiter="\t"))
    first_values = [float(value) for value in rows[1][1:]]
    checks.require(all(abs(actual - wanted) < 1e-12 for actual, wanted in zip(first_values, expected["first_row"])), "flow first row differs")
    event_hash = sha256_bytes(outputs[0])
    report_hash = sha256_bytes(outputs[1])
    checks.require(event_hash == case["output_sha256"]["events"], "flow event output hash differs")
    checks.require(report_hash == case["output_sha256"]["report"], "flow report output hash differs")
    before = [sha256_file(first_root / name) for name in ("compensated.tsv", "report.json")]
    overwrite = run_cli(SCRIPTS["flow_compensation"], arguments, first_root)
    checks.require(overwrite.returncode != 0, "flow overwrite was accepted")
    checks.require(before == [sha256_file(first_root / name) for name in ("compensated.tsv", "report.json")], "flow overwrite changed outputs")
    invalid_root = new_run_root(root, "flow-invalid")
    materialize(case, "events", "events.tsv", invalid_root, checks)
    materialize(case, "invalid_spillover", "invalid-spillover.tsv", invalid_root, checks)
    invalid = run_cli(
        SCRIPTS["flow_compensation"],
        ["--events", "events.tsv", "--spillover", "invalid-spillover.tsv", "--output-events", "invalid.tsv", "--output-report", "invalid.json"],
        invalid_root,
    )
    checks.require(invalid.returncode == 2, "flow invalid matrix was accepted")
    invalid_event = parse_event(invalid.stderr)
    checks.require(invalid_event.get("status") == "needs-decision", "flow invalid status differs")
    checks.require(invalid_event.get("code") == "nonunit-spillover-diagonal", "flow invalid classification differs")
    checks.require(not (invalid_root / "invalid.tsv").exists() and not (invalid_root / "invalid.json").exists(), "flow invalid run created output")
    return {"events": event_hash, "report": report_hash}


def check_km(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        materialize(case, "table", "subjects.tsv", run_root, checks)
        return ["--input", "subjects.tsv", "--output", "km.json"]

    outputs, first_root, arguments = run_twice(
        root, "km", setup, SCRIPTS["kaplan_meier"], ("km.json",), checks
    )
    report = strict_json_loads(outputs[0])
    expected = case["expected"]
    overall = report["overall"]
    checks.require(overall["subject_count"] == expected["subjects"], "KM subjects differ")
    checks.require(overall["event_count"] == expected["events"], "KM events differ")
    checks.require(overall["censor_count"] == expected["censors"], "KM censors differ")
    checks.require(overall["median"]["time"] == expected["median"], "KM median differs")
    groups = {item["group"]: item for item in report["groups"]}
    checks.require(groups["A"]["median"]["time"] == expected["group_A_median"], "KM group A median differs")
    checks.require(groups["B"]["median"]["time"] == expected["group_B_median"], "KM group B median differs")
    output_hash = sha256_bytes(outputs[0])
    checks.require(output_hash == case["output_sha256"], "KM output hash differs")
    before = sha256_file(first_root / "km.json")
    overwrite = run_cli(SCRIPTS["kaplan_meier"], arguments, first_root)
    checks.require(overwrite.returncode != 0, "KM overwrite was accepted")
    checks.require(sha256_file(first_root / "km.json") == before, "KM overwrite changed output")
    invalid_root = new_run_root(root, "km-invalid")
    materialize(case, "invalid_table", "invalid.tsv", invalid_root, checks)
    invalid = run_cli(SCRIPTS["kaplan_meier"], ["--input", "invalid.tsv", "--output", "invalid.json"], invalid_root)
    checks.require(invalid.returncode == 2, "KM invalid event was accepted")
    checks.require(parse_event(invalid.stderr).get("status") == "invalid-input", "KM invalid status differs")
    checks.require(not (invalid_root / "invalid.json").exists(), "KM invalid run created output")
    return {"report": output_hash}


def synthetic_provenance(case: dict[str, Any], payload: bytes) -> bytes:
    identifier = case["identifier"]
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        f"db=clinvar&rettype=vcv&id={identifier}"
    )
    value = {
        "schema_version": "0.1.0",
        "bytes": len(payload),
        "started_at": "2026-02-03T00:00:00Z",
        "completed_at": "2026-02-03T00:00:01Z",
        "execution_mode": "live-public-read-only",
        "max_response_bytes": 16 * 1024 * 1024,
        "method": "GET",
        "network_performed": True,
        "optional_api_key_applied": False,
        "optional_contact_applied": False,
        "output_file": case["payload_filename"],
        "pages": 1,
        "paid_use_authorized": False,
        "provider_documentation": "https://www.ncbi.nlm.nih.gov/books/NBK25497/",
        "provider_id": "ncbi-eutils",
        "request_urls": [url],
        "responses": [{
            "response_url": url,
            "content_type": "text/xml; charset=UTF-8",
            "etag": None,
            "last_modified": None,
            "page_value": None,
            "status": 200,
        }],
        "sha256": sha256_bytes(payload),
        "terms_acknowledged": False,
    }
    return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")


def check_clinvar(case: dict[str, Any], root: Path, checks: Checks) -> dict[str, str]:
    def setup(run_root: Path) -> list[str]:
        payload_path = materialize(case, "payload", case["payload_filename"], run_root, checks)
        sidecar = synthetic_provenance(case, payload_path.read_bytes())
        checks.require(sha256_bytes(sidecar) == case["input_sha256"]["synthetic_provenance"], "ClinVar provenance fixture hash differs")
        Path(str(payload_path) + ".provenance.json").write_bytes(sidecar)
        return ["--identifier", case["identifier"], "--input", case["payload_filename"], "--output", "clinvar.json"]

    outputs, first_root, arguments = run_twice(
        root, "clinvar", setup, SCRIPTS["clinvar_evidence"], ("clinvar.json",), checks
    )
    report = strict_json_loads(outputs[0])
    expected = case["expected"]
    checks.require(report["returned_record_count"] == expected["records"], "ClinVar record count differs")
    checks.require(len(report["records"][0]["clinical_assertions"]) == expected["assertions"], "ClinVar assertion count differs")
    checks.require(
        report["records"][0]["aggregate_classifications"][0]["review_statuses"]
        == [expected["aggregate_review_status"]],
        "ClinVar aggregate review status differs",
    )
    checks.require(report["conflict_resolution"] == expected["conflict_resolution"], "ClinVar conflict boundary differs")
    output_hash = sha256_bytes(outputs[0])
    checks.require(output_hash == case["output_sha256"], "ClinVar output hash differs")
    before = sha256_file(first_root / "clinvar.json")
    overwrite = run_cli(SCRIPTS["clinvar_evidence"], arguments, first_root)
    checks.require(overwrite.returncode != 0, "ClinVar overwrite was accepted")
    checks.require(sha256_file(first_root / "clinvar.json") == before, "ClinVar overwrite changed output")
    invalid_root = new_run_root(root, "clinvar-invalid")
    invalid_arguments = setup(invalid_root)
    sidecar_path = invalid_root / f"{case['payload_filename']}.provenance.json"
    sidecar = strict_json_loads(sidecar_path.read_bytes())
    sidecar["sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar, sort_keys=True) + "\n", encoding="utf-8")
    invalid = run_cli(SCRIPTS["clinvar_evidence"], invalid_arguments, invalid_root)
    checks.require(invalid.returncode == 2, "ClinVar unbound provenance was accepted")
    checks.require(parse_event(invalid.stderr).get("status") == "invalid-input", "ClinVar invalid status differs")
    checks.require(not (invalid_root / "clinvar.json").exists(), "ClinVar invalid run created output")
    return {"report": output_hash}


def main() -> int:
    fixture = strict_json_loads(FIXTURE.read_bytes())
    if not isinstance(fixture, dict):
        raise ValueError("fixture root is not an object")
    checks = Checks()
    package_bindings = check_package_bindings(fixture, checks)
    with tempfile.TemporaryDirectory(prefix="bio02-wave-r4-minimum-") as temporary:
        root = Path(temporary)
        check_self_tests(fixture, root, checks)
        output_hashes = {
            PACKAGES["bulk_gene_counting"]: check_bulk(fixture["bulk_gene_counting"], root, checks),
            PACKAGES["junction_psi"]: check_junction(fixture["junction_psi"], root, checks),
            PACKAGES["alpha_diversity"]: check_alpha(fixture["alpha_diversity"], root, checks),
            PACKAGES["flow_compensation"]: check_flow(fixture["flow_compensation"], root, checks),
            PACKAGES["kaplan_meier"]: check_km(fixture["kaplan_meier"], root, checks),
            PACKAGES["clinvar_evidence"]: check_clinvar(fixture["clinvar_evidence"], root, checks),
        }
    print(json.dumps({
        "checks": checks.count,
        "fixture_sha256": sha256_file(FIXTURE),
        "network_performed": False,
        "output_sha256": output_hashes,
        "package_digests": package_bindings,
        "status": "pass",
        "synthetic_clinvar_provenance": True,
        "version": VERSION,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "status": "fail", "version": VERSION}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
