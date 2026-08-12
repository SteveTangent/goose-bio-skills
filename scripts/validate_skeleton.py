#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the source-clean installable-package boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_VERSION = "1.1.0"
PUBLIC_PACKAGE_VERSION = "0.7.0"
MANIFEST_SCHEMA_VERSION = "0.2.0"
REGISTRY_SCHEMA_VERSION = "0.5.0"
PROVIDER_CATALOG_SCHEMA_VERSION = "0.2.0"
LICENSE_ID = "Apache-2.0"
APACHE_LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
ERRORS: list[str] = []

INTAKE_CONTRACT_VERSION = "1.3.0"
INTAKE_POLICY = {
    "facts_before_questions": True,
    "question_policy": "one-unresolved-load-bearing-decision-at-a-time-with-recommendation",
    "wait_after_each_question": True,
    "explicit_safe_local_execution": "proceed-without-repeat-confirmation",
    "side_effect_confirmation": "only-when-not-already-authorized-for-current-action-and-scope",
}
DECISION_FIELDS = {
    "decision_id",
    "applies_when",
    "question",
    "recommended_answer",
}
INTAKE_EVAL_SCHEMA_VERSION = "0.1.0"
INTAKE_EVAL_FIELDS = {
    "schema_version",
    "evidence_kind",
    "assurance_note",
    "cases",
}
INTAKE_CASE_FIELDS = {
    "id",
    "prompt",
    "expected_skill",
    "forbidden_skills",
    "expected_action",
    "expected_question_count_this_turn",
    "expected_first_decision_id",
}
CRITICAL_INTAKE_CASES = {
    "raw-count-de-routes-away-from-pvalue-helper": (
        "count-based-differential-expression",
        0,
        None,
    ),
    "pvalues-fully-specified-local": (
        "statistical-analysis-and-multiple-testing",
        0,
        None,
    ),
    "remote-blast-prohibited-patient-data": (
        "sequence-similarity-and-homology-search",
        0,
        None,
    ),
    "remote-blast-sensitive-authorization": (
        "sequence-similarity-and-homology-search",
        1,
        "remote-data-authorization",
    ),
    "remote-blast-sensitive-confirmation-resolves-on-follow-up": (
        "sequence-similarity-and-homology-search",
        0,
        None,
    ),
    "remote-blast-explicit-nonsensitive-no-repeat": (
        "sequence-similarity-and-homology-search",
        0,
        None,
    ),
    "vcf-missing-reference-first": (
        "vcf-normalization-qc-and-query",
        1,
        "vcf-reference",
    ),
    "vcf-fully-specified-no-repeat": (
        "vcf-normalization-qc-and-query",
        0,
        None,
    ),
    "run-manifest-exact-accession-no-question": (
        "public-sequencing-run-manifest-retrieval",
        0,
        None,
    ),
    "run-manifest-unbounded-scope-asks-once": (
        "public-sequencing-run-manifest-retrieval",
        1,
        "manifest-scope",
    ),
    "taxonomy-taxids-no-question": (
        "taxonomy-name-and-taxid-resolution",
        0,
        None,
    ),
    "taxonomy-ambiguous-name-asks-once": (
        "taxonomy-name-and-taxid-resolution",
        1,
        "ambiguous-name-match",
    ),
    "raw-read-qc-existing-reports-no-question": (
        "raw-read-quality-reporting",
        0,
        None,
    ),
    "raw-read-qc-missing-library-context": (
        "raw-read-quality-reporting",
        1,
        "library-context",
    ),
    "run-study-discovery-routes-away": (
        "biomedical-literature-and-public-study-search",
        0,
        None,
    ),
    "taxonomy-gene-mapping-routes-away": (
        "biological-database-record-retrieval-and-identifier-resolution",
        0,
        None,
    ),
    "raw-read-trimming-routes-away": (
        None,
        0,
        None,
    ),
    "raw-trimming-fully-specified-small-local": (
        "raw-read-trimming-and-filtering",
        0,
        None,
    ),
    "raw-trimming-missing-adapter-first": (
        "raw-read-trimming-and-filtering",
        1,
        "adapter-policy",
    ),
    "raw-demultiplexing-routes-away": (
        None,
        0,
        None,
    ),
    "gff-qc-fully-specified-local": (
        "gff-gtf-gene-model-qc",
        0,
        None,
    ),
    "gff-qc-missing-dialect-first": (
        "gff-gtf-gene-model-qc",
        1,
        "annotation-dialect",
    ),
    "gff-interval-overlap-routes-away": (
        "genomic-interval-operations",
        0,
        None,
    ),
    "fcs-metadata-fully-specified-local": (
        "fcs-file-io-and-metadata-qc",
        0,
        None,
    ),
    "fcs-multiple-datasets-asks-scope": (
        "fcs-file-io-and-metadata-qc",
        1,
        "fcs-dataset-scope",
    ),
    "missing-data-specified-local": (
        "missing-data-and-sensitivity-analysis",
        0,
        None,
    ),
    "protein-interface-explicit-chains-cutoff": (
        "protein-interface-contact-analysis",
        0,
        None,
    ),
    "public-orthology-exact-identifiers": (
        "public-orthology-retrieval-and-qc",
        0,
        None,
    ),
    "fcs-gating-analysis-routes-away": (
        None,
        0,
        None,
    ),
}
RESEARCH_R1_HOLDOUT_ORACLES = {
    "missing-r1-blind-positive": (
        "missing-data-and-sensitivity-analysis",
        0,
        None,
    ),
    "missing-r1-blind-neighbor-multiplicity": (
        "statistical-analysis-and-multiple-testing",
        0,
        None,
    ),
    "contacts-r1-blind-positive": (
        "protein-interface-contact-analysis",
        0,
        None,
    ),
    "contacts-r1-blind-adversarial-cif": (
        None,
        0,
        None,
    ),
    "orthology-r1-blind-positive": (
        "public-orthology-retrieval-and-qc",
        0,
        None,
    ),
    "orthology-r1-blind-neighbor-sequence": (
        "sequence-similarity-and-homology-search",
        0,
        None,
    ),
}

RELEASE_STAGES = {"preview", "stable"}
ASSURANCE_LEVELS = {"reviewed", "evaluated"}
NETWORK_MODES = {"none", "optional", "required"}
ALLOWED_LIFECYCLES = {
    ("preview", "reviewed"),
    ("preview", "evaluated"),
    ("stable", "evaluated"),
}
REGISTRY_LIFECYCLE_AXES = {
    "release_stage": ["preview", "stable"],
    "assurance_level": ["reviewed", "evaluated"],
    "allowed_combinations": [
        "preview+reviewed",
        "preview+evaluated",
        "stable+evaluated",
    ],
}
ASSURANCE_FIELDS = {
    "runtime_evaluation",
    "scientific_benchmark",
    "human_expert_review",
    "better_than_baseline_claim",
    "clinical_use",
    "unverified_boundaries",
}
SCRIPT_VERIFICATION_FIELDS = {
    "bundled_scripts",
    "implementation_origin",
    "self_test_status",
    "self_test_command",
    "runtime_versions",
}
RUNTIME_VERIFICATION_FIELDS = {
    "mode",
    "status",
    "reason",
    "tool_versions",
    "unverified_boundaries",
}
LEGAL_NOTICE_FIELDS = {"required", "files"}
ROLLBACK_FIELDS = {"previous_version", "boundary"}
PROVIDER_FIELDS = {
    "display_name",
    "purpose",
    "would_send",
    "credential_fields",
    "billing",
    "allowed_hosts",
    "execution",
    "official_docs",
}
PROVIDER_CATALOG_FIELDS = {
    "schema_version",
    "mode",
    "freshness_checked_at",
    "provider_ids",
    "providers",
}
DEPRECATED_MANIFEST_FIELDS = {"requires_network", "optional_adapters"}
PROVIDER_EXECUTION_FIELDS = {
    "execution_mode",
    "allowed_url_prefixes",
    "rate_limit_per_second",
    "max_response_bytes",
}
PROVIDER_EXECUTION_MODES = {
    "direct-read",
    "terms-read",
    "conditional-job",
    "disabled",
}
EXTERNAL_SERVICE_BOUNDARY_CONTRACT = {
    "public_access": "explicit-request-authorizes-bounded-read-download",
    "confirmation": "sensitive-upload-remote-job-bulk-or-paid",
    "config_access": "shared-companion-reads-no-provider-config-or-credentials",
    "credential_policy": "shared-companion-anonymous-only",
    "standalone_fallback": "needs-tool-dry-run-or-partial",
    "call_claim": "only-after-checked-live-response",
}
GENERIC_APPLIES_WHEN = (
    "this Skill is correctly routed and this decision affects the requested result or execution contract"
)
LEGAL_NOTICE_PREFIXES = (
    "LICENSE",
    "NOTICE",
    "COPYING",
    "COPYRIGHT",
    "ATTRIBUTION",
    "THIRD_PARTY_NOTICES",
    "THIRD-PARTY-NOTICES",
)
CODE_SUFFIXES = {".py", ".r", ".sh", ".bash", ".zsh", ".pl", ".rb", ".js", ".ts"}
SOURCE_SCAN_EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
PREVIEW_POSITIVE_CLAIMS = (
    re.compile(r"\b(?:is|are|was|were|has been|have been)\s+(?:fully\s+|scientifically\s+)?validated\b", re.I),
    re.compile(r"\b(?:is|are|was|were)\s+better than (?:a |the |no-skill )?baseline\b", re.I),
    re.compile(r"\boutperforms? (?:a |the |no-skill )?baseline\b", re.I),
    re.compile(r"\bproven (?:better|superior)\b", re.I),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def nonempty_strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and bool(item.strip()) for item in value)


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_date(value: object) -> bool:
    if not nonempty_string(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


class DuplicateJSONKeyError(ValueError):
    """A JSON object contains an ambiguous repeated member name."""


def json_loads_no_duplicates(text: str) -> object:
    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateJSONKeyError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs_hook)


def load_json(relative_path: str) -> object:
    path = ROOT / relative_path
    try:
        return json_loads_no_duplicates(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJSONKeyError) as exc:
        ERRORS.append(f"{relative_path}: invalid or unreadable JSON: {exc}")
        return {}


def validate_connector_catalog() -> set[str]:
    catalog = load_json("connectors/providers.json")
    require(isinstance(catalog, dict), "connector catalog: expected an object")
    if not isinstance(catalog, dict):
        return set()
    require(set(catalog) == PROVIDER_CATALOG_FIELDS, "connector catalog: unexpected top-level fields")
    require(
        catalog.get("schema_version") == PROVIDER_CATALOG_SCHEMA_VERSION,
        "connector catalog: wrong schema version",
    )
    require(
        catalog.get("mode") == "live-public-read-only",
        "connector catalog: mode must be live-public-read-only",
    )
    require(valid_date(catalog.get("freshness_checked_at")), "connector catalog: invalid freshness date")
    provider_ids = catalog.get("provider_ids")
    providers = catalog.get("providers")
    require(nonempty_strings(provider_ids) and bool(provider_ids), "connector catalog: provider_ids must be non-empty")
    require(isinstance(providers, dict) and bool(providers), "connector catalog: providers must be non-empty")
    if not isinstance(provider_ids, list) or not isinstance(providers, dict):
        return set()
    if nonempty_strings(provider_ids):
        require(len(provider_ids) == len(set(provider_ids)), "connector catalog: duplicate provider ID")
    require(provider_ids == list(providers), "connector catalog: provider_ids must match provider keys in order")
    for provider_id, provider in providers.items():
        label = f"connector catalog provider {provider_id}"
        require(
            isinstance(provider_id, str) and bool(re.fullmatch(r"[a-z0-9-]+", provider_id)),
            f"{label}: invalid provider ID",
        )
        require(isinstance(provider, dict), f"{label}: expected an object")
        if not isinstance(provider, dict):
            continue
        require(set(provider) == PROVIDER_FIELDS, f"{label}: fields do not match catalog contract")
        for field in ("display_name", "purpose", "official_docs"):
            require(nonempty_string(provider.get(field)), f"{label}: {field} must be non-empty")
        require(
            isinstance(provider.get("official_docs"), str)
            and str(provider.get("official_docs")).startswith("https://"),
            f"{label}: official_docs must use HTTPS",
        )
        for field in ("would_send", "allowed_hosts"):
            values = provider.get(field)
            require(nonempty_strings(values) and bool(values), f"{label}: {field} must be non-empty")
            if nonempty_strings(values):
                require(len(values) == len(set(values)), f"{label}: {field} contains duplicates")
        require(isinstance(provider.get("credential_fields"), list), f"{label}: credential_fields must be a list")
        billing = provider.get("billing")
        require(isinstance(billing, dict), f"{label}: billing must be an object")
        execution = provider.get("execution")
        require(isinstance(execution, dict), f"{label}: execution must be an object")
        if not isinstance(execution, dict):
            continue
        require(
            set(execution) == PROVIDER_EXECUTION_FIELDS,
            f"{label}: execution fields do not match catalog contract",
        )
        mode = execution.get("execution_mode")
        prefixes = execution.get("allowed_url_prefixes")
        rate = execution.get("rate_limit_per_second")
        max_bytes = execution.get("max_response_bytes")
        require(mode in PROVIDER_EXECUTION_MODES, f"{label}: invalid execution_mode")
        require(nonempty_strings(prefixes) and bool(prefixes), f"{label}: allowed_url_prefixes must be non-empty")
        require(
            isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate >= 0,
            f"{label}: invalid rate_limit_per_second",
        )
        require(
            isinstance(max_bytes, int) and not isinstance(max_bytes, bool) and max_bytes >= 0,
            f"{label}: invalid max_response_bytes",
        )
        active = mode in {"direct-read", "terms-read"}
        if active:
            require(bool(rate and rate > 0), f"{label}: active provider needs a positive rate limit")
            require(bool(max_bytes and max_bytes > 0), f"{label}: active provider needs a positive byte limit")
            if isinstance(billing, dict):
                require(
                    billing.get("requires_separate_paid_authorization") is False,
                    f"{label}: paid provider cannot be directly executable",
                )
        else:
            require(rate == 0 and max_bytes == 0, f"{label}: inactive provider limits must be zero")
        hosts = provider.get("allowed_hosts")
        if isinstance(prefixes, list) and isinstance(hosts, list):
            for prefix in prefixes:
                parsed = urlsplit(prefix) if isinstance(prefix, str) else None
                require(
                    parsed is not None
                    and parsed.scheme == "https"
                    and parsed.hostname in hosts,
                    f"{label}: executable URL prefix escapes allowed_hosts",
                )
    return {item for item in provider_ids if isinstance(item, str)}


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def parse_frontmatter_scalar(raw: str, label: str, field: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if field in {"description", "version"} and not (
        value.startswith('"') and value.endswith('"')
    ):
        ERRORS.append(f"{label}: {field} must be a double-quoted text scalar")
        return ""
    if field in {"name", "license"} and any(
        character in value for character in {'"', "'"}
    ):
        ERRORS.append(f"{label}: {field} must use the canonical plain scalar form")
        return ""
    if value in {">", ">-", ">+", "|", "|-", "|+"}:
        ERRORS.append(f"{label}: YAML block scalars are not supported in package frontmatter")
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            ERRORS.append(f"{label}: unterminated frontmatter scalar")
            return ""
        if quote == '"':
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                ERRORS.append(f"{label}: invalid double-quoted frontmatter scalar")
                return ""
            if not isinstance(decoded, str):
                ERRORS.append(f"{label}: frontmatter scalar must be text")
                return ""
            return decoded
        inner = value[1:-1]
        if "'" in inner.replace("''", ""):
            ERRORS.append(f"{label}: invalid single-quoted frontmatter scalar")
            return ""
        return inner.replace("''", "'")
    if any(character in value for character in {'"', "'"}):
        ERRORS.append(f"{label}: stray quote in frontmatter scalar")
        return ""
    return value


def read_frontmatter(path: Path) -> dict[str, object]:
    label = display_path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        ERRORS.append(f"{label}: unreadable: {exc}")
        return {}
    if not lines or lines[0] != "---":
        ERRORS.append(f"{label}: missing frontmatter")
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        ERRORS.append(f"{label}: unterminated frontmatter")
        return {}
    fields: dict[str, object] = {}
    active_mapping: dict[str, str] | None = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            ERRORS.append(f"{label}: malformed frontmatter line")
            continue
        if line[0].isspace():
            if active_mapping is None or not line.startswith("  ") or line.startswith("   "):
                ERRORS.append(f"{label}: unexpected nested frontmatter field")
                continue
            key, value = line.strip().split(":", 1)
            if key in active_mapping:
                ERRORS.append(f"{label}: duplicate nested frontmatter field: {key}")
                continue
            active_mapping[key] = parse_frontmatter_scalar(value, label, key)
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in fields:
            ERRORS.append(f"{label}: duplicate frontmatter field: {key}")
            continue
        scalar = parse_frontmatter_scalar(value, label, key)
        if key == "metadata" and not scalar:
            active_mapping = {}
            fields[key] = active_mapping
        else:
            active_mapping = None
            fields[key] = scalar
    return fields


def validate_frontmatter(
    frontmatter: dict[str, object],
    *,
    expected_name: str,
    expected_version: str,
    label: str,
) -> None:
    require(
        set(frontmatter) == {"name", "description", "license", "metadata"},
        f"{label}: frontmatter fields differ",
    )
    name = frontmatter.get("name")
    require(name == expected_name, f"{label}: frontmatter name mismatch")
    require(
        isinstance(name, str)
        and 1 <= len(name) <= 64
        and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)),
        f"{label}: invalid frontmatter name",
    )
    description = frontmatter.get("description")
    require(
        nonempty_string(description) and isinstance(description, str) and len(description) <= 1024,
        f"{label}: frontmatter description is required",
    )
    require(frontmatter.get("license") == LICENSE_ID, f"{label}: frontmatter license must be {LICENSE_ID}")
    metadata = frontmatter.get("metadata")
    require(isinstance(metadata, dict), f"{label}: frontmatter metadata must be a mapping")
    if isinstance(metadata, dict):
        require(set(metadata) == {"version"}, f"{label}: frontmatter metadata fields differ")
        require(
            metadata.get("version") == expected_version,
            f"{label}: frontmatter metadata version mismatch",
        )


def validate_apache_license(path: Path, label: str) -> None:
    require(path.is_file() and not path.is_symlink(), f"{label}: Apache-2.0 LICENSE is missing or symlinked")
    if path.is_file() and not path.is_symlink():
        require(
            sha256_file(path) == APACHE_LICENSE_SHA256,
            f"{label}: Apache-2.0 LICENSE bytes differ from the canonical text",
        )


def validate_spdx_header(path: Path, label: str) -> None:
    try:
        first_lines = path.read_text(encoding="utf-8").splitlines()[:5]
    except OSError as exc:
        require(False, f"{label}: unreadable Python source: {exc}")
        return
    require(
        "# SPDX-License-Identifier: Apache-2.0" in first_lines,
        f"{label}: missing Apache-2.0 SPDX header",
    )


def python_sources(root: Path) -> list[Path]:
    return sorted(
        item for item in root.rglob("*") if item.is_file() and item.suffix.lower() == ".py"
    )


def validate_manifest_intake(manifest: dict[str, object], label: str) -> None:
    require(
        manifest.get("intake_contract_version") == INTAKE_CONTRACT_VERSION,
        f"{label}: wrong intake contract version",
    )
    intake_contract = manifest.get("intake_contract")
    require(isinstance(intake_contract, dict), f"{label}: intake contract must be an object")
    if not isinstance(intake_contract, dict):
        return

    decision_sequence = intake_contract.get("decision_sequence")
    contract_without_sequence = {
        key: value for key, value in intake_contract.items() if key != "decision_sequence"
    }
    require(contract_without_sequence == INTAKE_POLICY, f"{label}: intake contract does not match policy")
    require(isinstance(decision_sequence, list), f"{label}: decision sequence must be a list")
    if not isinstance(decision_sequence, list):
        return

    seen_ids: set[str] = set()
    for decision in decision_sequence:
        require(isinstance(decision, dict), f"{label}: every decision must be an object")
        if not isinstance(decision, dict):
            continue
        require(set(decision) == DECISION_FIELDS, f"{label}: decision fields do not match policy")
        decision_id = decision.get("decision_id")
        require(isinstance(decision_id, str) and bool(decision_id), f"{label}: decision_id must be non-empty")
        if not isinstance(decision_id, str) or not decision_id:
            continue
        require(decision_id not in seen_ids, f"{label}: duplicate decision_id")

        applies_when = decision.get("applies_when")
        require(
            nonempty_string(applies_when),
            f"{label}: applies_when must be a non-empty string",
        )
        if isinstance(applies_when, str):
            require(
                applies_when.strip() != GENERIC_APPLIES_WHEN,
                f"{label}: applies_when must name a concrete unresolved condition",
            )

        question = decision.get("question")
        require(isinstance(question, str) and question.endswith("?"), f"{label}: decision question must end in ?")
        recommended = decision.get("recommended_answer")
        require(isinstance(recommended, str) and bool(recommended), f"{label}: recommended answer must be non-empty")
        seen_ids.add(decision_id)


def validate_assurance(manifest: dict[str, object], label: str) -> None:
    release_stage = manifest.get("release_stage")
    assurance_level = manifest.get("assurance_level")
    require(manifest.get("status") == "active", f"{label}: status must be active")
    require(
        manifest.get("lifecycle_stage") == "production",
        f"{label}: lifecycle_stage must be production",
    )
    require(
        manifest.get("distribution_status") == "installable",
        f"{label}: distribution_status must be installable",
    )
    require(isinstance(release_stage, str) and release_stage in RELEASE_STAGES, f"{label}: invalid release_stage")
    require(isinstance(assurance_level, str) and assurance_level in ASSURANCE_LEVELS, f"{label}: invalid assurance_level")
    require(
        isinstance(release_stage, str)
        and isinstance(assurance_level, str)
        and (release_stage, assurance_level) in ALLOWED_LIFECYCLES,
        f"{label}: invalid lifecycle combination",
    )

    assurance = manifest.get("assurance")
    require(isinstance(assurance, dict), f"{label}: assurance must be an object")
    if not isinstance(assurance, dict):
        return
    require(set(assurance) == ASSURANCE_FIELDS, f"{label}: assurance fields do not match policy")
    runtime = assurance.get("runtime_evaluation")
    benchmark = assurance.get("scientific_benchmark")
    human_review = assurance.get("human_expert_review")
    require(isinstance(runtime, str) and runtime in {"not-performed", "bounded-exact-package"}, f"{label}: invalid runtime_evaluation")
    require(isinstance(benchmark, str) and benchmark in {"not-performed", "bounded"}, f"{label}: invalid scientific_benchmark")
    require(isinstance(human_review, str) and human_review in {"not-performed", "bounded"}, f"{label}: invalid human_expert_review")
    require(assurance.get("better_than_baseline_claim") is False, f"{label}: baseline-superiority claims are forbidden")
    require(assurance.get("clinical_use") == "prohibited", f"{label}: clinical_use must be prohibited")
    boundaries = assurance.get("unverified_boundaries")
    require(nonempty_strings(boundaries), f"{label}: unverified_boundaries must be a string list")
    if isinstance(boundaries, list):
        require(
            not any(
                isinstance(item, str)
                and "outbound project license" in item.casefold()
                for item in boundaries
            ),
            f"{label}: obsolete outbound-license boundary is forbidden",
        )

    if assurance_level == "reviewed":
        require(runtime == "not-performed", f"{label}: reviewed assurance cannot claim runtime evaluation")
        require(benchmark == "not-performed", f"{label}: reviewed assurance cannot claim a scientific benchmark")
        require(bool(boundaries), f"{label}: reviewed assurance must state unverified boundaries")
    if assurance_level == "evaluated":
        require(runtime == "bounded-exact-package", f"{label}: evaluated assurance needs bounded exact-package evidence")


def validate_script_verification(
    manifest: dict[str, object],
    label: str,
    has_scripts: bool,
) -> None:
    verification = manifest.get("script_verification")
    require(isinstance(verification, dict), f"{label}: script_verification must be an object")
    if not isinstance(verification, dict):
        return
    require(set(verification) == SCRIPT_VERIFICATION_FIELDS, f"{label}: script_verification fields do not match policy")
    require(verification.get("bundled_scripts") is has_scripts, f"{label}: bundled_scripts differs from package contents")

    status = verification.get("self_test_status")
    command = verification.get("self_test_command")
    runtime_versions = verification.get("runtime_versions")
    require(nonempty_strings(runtime_versions), f"{label}: runtime_versions must be a string list")

    if not has_scripts:
        require(verification.get("implementation_origin") == "none", f"{label}: script origin must be none")
        require(status == "not-applicable", f"{label}: script self-test must be not-applicable")
        require(command is None, f"{label}: script command must be null")
        require(runtime_versions == [], f"{label}: no-script runtime_versions must be empty")
        return

    require(
        verification.get("implementation_origin")
        in {"original-new", "original-rewrite-after-private-evaluation"},
        f"{label}: bundled scripts must be original implementations",
    )
    require(status == "passed", f"{label}: every bundled script needs a passed deterministic self-test")
    require(nonempty_string(command), f"{label}: self-test command must be recorded")
    require(bool(runtime_versions), f"{label}: bundled script runtime_versions must be recorded")


def validate_runtime_verification(manifest: dict[str, object], label: str) -> None:
    verification = manifest.get("runtime_verification")
    require(isinstance(verification, dict), f"{label}: runtime_verification must be an object")
    if not isinstance(verification, dict):
        return
    require(set(verification) == RUNTIME_VERIFICATION_FIELDS, f"{label}: runtime_verification fields do not match policy")

    mode = verification.get("mode")
    status = verification.get("status")
    reason = verification.get("reason")
    tool_versions = verification.get("tool_versions")
    boundaries = verification.get("unverified_boundaries")
    require(nonempty_strings(tool_versions), f"{label}: runtime tool_versions must be a string list")
    require(nonempty_strings(boundaries), f"{label}: runtime unverified_boundaries must be a string list")
    require(
        mode in {"not-performed", "bounded-exact-package", "skipped-complex-tool"},
        f"{label}: invalid runtime verification mode",
    )

    if mode == "not-performed":
        require(status == "not-performed", f"{label}: not-performed runtime status mismatch")
        require(nonempty_string(reason), f"{label}: not-performed runtime verification needs a reason")
        require(bool(boundaries), f"{label}: not-performed runtime verification needs an unverified boundary")
    elif mode == "bounded-exact-package":
        require(status == "passed", f"{label}: bounded runtime verification must have passed")
        require(reason is None, f"{label}: passed bounded runtime verification cannot have a skip reason")
    elif mode == "skipped-complex-tool":
        require(status == "skipped", f"{label}: complex-tool skip status mismatch")
        require(nonempty_string(reason), f"{label}: complex-tool skip needs a reason")
        require(bool(tool_versions), f"{label}: complex-tool skip needs relevant tool versions")
        require(bool(boundaries), f"{label}: complex-tool skip needs unverified boundaries")

    assurance = manifest.get("assurance")
    if not isinstance(assurance, dict):
        return
    expected_runtime = "bounded-exact-package" if mode == "bounded-exact-package" else "not-performed"
    require(
        assurance.get("runtime_evaluation") == expected_runtime,
        f"{label}: runtime verification disagrees with assurance.runtime_evaluation",
    )
    assurance_boundaries = assurance.get("unverified_boundaries")
    if nonempty_strings(assurance_boundaries) and nonempty_strings(boundaries):
        require(
            set(boundaries).issubset(set(assurance_boundaries)),
            f"{label}: runtime boundaries must also appear in assurance.unverified_boundaries",
        )


def validate_rollback(manifest: dict[str, object], label: str) -> None:
    rollback = manifest.get("rollback")
    require(isinstance(rollback, dict), f"{label}: rollback must be an object")
    if not isinstance(rollback, dict):
        return
    require(set(rollback) == ROLLBACK_FIELDS, f"{label}: rollback fields do not match policy")
    previous = rollback.get("previous_version")
    require(previous is None or (isinstance(previous, str) and bool(SEMVER.fullmatch(previous))), f"{label}: invalid rollback previous_version")
    require(previous != manifest.get("version"), f"{label}: rollback cannot target the same version")
    require(nonempty_string(rollback.get("boundary")), f"{label}: rollback boundary must be non-empty")
    if manifest.get("release_stage") == "stable":
        require(previous is not None, f"{label}: stable release needs a previous rollback version")


def validate_legal_notices(
    manifest: dict[str, object],
    label: str,
    package: Path | None,
) -> None:
    notices = manifest.get("legal_notices")
    require(isinstance(notices, dict), f"{label}: legal_notices must be an object")
    if not isinstance(notices, dict):
        return
    require(set(notices) == LEGAL_NOTICE_FIELDS, f"{label}: legal_notices fields do not match policy")
    required = notices.get("required")
    files = notices.get("files")
    require(isinstance(required, bool), f"{label}: legal_notices.required must be boolean")
    require(nonempty_strings(files), f"{label}: legal_notices.files must be a string list")
    if not isinstance(files, list):
        return
    require(required is True, f"{label}: Apache-2.0 LICENSE must be required")
    require(bool(files) and files[0] == "LICENSE", f"{label}: legal_notices.files must start with LICENSE")
    require(len(files) == len(set(files)), f"{label}: legal_notices.files contains duplicates")
    for item in files:
        if not isinstance(item, str):
            continue
        relative = Path(item)
        require(not relative.is_absolute() and ".." not in relative.parts, f"{label}: unsafe legal notice path")
        require(
            relative.name.upper().startswith(LEGAL_NOTICE_PREFIXES),
            f"{label}: unsupported legal notice filename",
        )
        if package is not None:
            require((package / relative).is_file(), f"{label}: declared legal notice is missing: {item}")
    if package is not None:
        validate_apache_license(package / "LICENSE", label)


def validate_manifest_policy(
    manifest: dict[str, object],
    label: str,
    package: Path | None = None,
    has_scripts: bool = False,
    allow_template_placeholders: bool = False,
    provider_ids: set[str] | None = None,
) -> None:
    required = {
        "schema_version",
        "name",
        "version",
        "maturity_tier",
        "context_budget_tier",
        "domain_id",
        "cluster_id",
        "risk_tier",
        "owner",
        "updated_at",
        "last_freshness_check",
        "review_cadence",
        "status",
        "lifecycle_stage",
        "distribution_status",
        "release_stage",
        "assurance_level",
        "assurance",
        "intake_contract_version",
        "intake_contract",
        "script_verification",
        "runtime_verification",
        "legal_notices",
        "rollback",
        "network_mode",
        "local_adapters",
        "external_services",
        "depends_on",
        "target_platforms",
    }
    require(required.issubset(manifest), f"{label}: missing required manifest fields")
    require(
        not DEPRECATED_MANIFEST_FIELDS.intersection(manifest),
        f"{label}: deprecated network fields are forbidden",
    )
    name = manifest.get("name")
    version = manifest.get("version")
    require(
        manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION,
        f"{label}: wrong manifest schema version",
    )
    require(isinstance(name, str) and bool(re.fullmatch(r"[a-z0-9-]+", name)), f"{label}: invalid name")
    require(isinstance(version, str) and bool(SEMVER.fullmatch(version)), f"{label}: invalid version")
    require(manifest.get("maturity_tier") == "production", f"{label}: maturity_tier must be production")
    require(
        manifest.get("context_budget_tier") == "production",
        f"{label}: context_budget_tier must be production",
    )
    require(isinstance(manifest.get("domain_id"), str) and bool(re.fullmatch(r"D[0-9]{2}", manifest["domain_id"])), f"{label}: invalid domain_id")
    require(isinstance(manifest.get("cluster_id"), str) and bool(re.fullmatch(r"C[0-9]{2}", manifest["cluster_id"])), f"{label}: invalid cluster_id")
    require(isinstance(manifest.get("risk_tier"), str) and bool(re.fullmatch(r"R[0-9]+", manifest["risk_tier"])), f"{label}: invalid risk_tier")
    require(nonempty_string(manifest.get("owner")), f"{label}: owner must be non-empty")
    if allow_template_placeholders:
        require(manifest.get("updated_at") == "YYYY-MM-DD", f"{label}: template updated_at placeholder changed")
        require(manifest.get("last_freshness_check") == "YYYY-MM-DD", f"{label}: template freshness placeholder changed")
    else:
        require(name != "replace-with-skill-name", f"{label}: unresolved name placeholder")
        require(manifest.get("owner") != "replace-with-owner", f"{label}: unresolved owner placeholder")
        require(manifest.get("domain_id") != "D00", f"{label}: unresolved domain placeholder")
        require(manifest.get("cluster_id") != "C00", f"{label}: unresolved cluster placeholder")
        require(valid_date(manifest.get("updated_at")), f"{label}: invalid updated_at")
        require(valid_date(manifest.get("last_freshness_check")), f"{label}: invalid last_freshness_check")
    require(
        manifest.get("review_cadence") in {"monthly", "quarterly", "semiannual", "annual", "per-release"},
        f"{label}: invalid review_cadence",
    )
    network_mode = manifest.get("network_mode")
    external_services = manifest.get("external_services")
    require(network_mode in NETWORK_MODES, f"{label}: invalid network_mode")
    for field in ("local_adapters", "external_services", "depends_on", "target_platforms"):
        values = manifest.get(field)
        require(nonempty_strings(values), f"{label}: {field} must be a string list")
        if nonempty_strings(values):
            require(len(values) == len(set(values)), f"{label}: {field} contains duplicates")
    if isinstance(external_services, list):
        require(
            all(isinstance(item, str) and bool(re.fullmatch(r"[a-z0-9-]+", item)) for item in external_services),
            f"{label}: external_services must contain provider IDs",
        )
        if network_mode == "none":
            require(not external_services, f"{label}: network_mode none cannot reference external services")
        elif network_mode in {"optional", "required"}:
            require(bool(external_services), f"{label}: networked package needs an external service")
        if provider_ids is not None:
            require(
                set(item for item in external_services if isinstance(item, str)).issubset(provider_ids),
                f"{label}: external_services contains an unknown provider ID",
            )
    validate_manifest_intake(manifest, label)
    validate_assurance(manifest, label)
    validate_script_verification(manifest, label, has_scripts)
    validate_runtime_verification(manifest, label)
    validate_legal_notices(manifest, label, package)
    validate_rollback(manifest, label)


def validate_dependency_references(
    manifests: dict[str, dict[str, object]],
) -> None:
    """Require each declared dependency to identify a different current package."""
    package_names = set(manifests)
    for name in sorted(manifests):
        dependencies = manifests[name].get("depends_on")
        if not isinstance(dependencies, list):
            continue
        for dependency in dependencies:
            if not isinstance(dependency, str):
                continue
            require(dependency != name, f"skills/{name}: cannot depend on itself")
            require(
                dependency in package_names,
                f"skills/{name}: depends_on references unknown package {dependency}",
            )


def validate_intake_routing_fixture(
    fixture: object,
    manifests: dict[str, dict[str, object]],
    label: str,
    *,
    expected_count: int,
    required_oracles: dict[str, tuple[str | None, int, str | None]],
) -> None:
    require(isinstance(fixture, dict), f"{label}: expected an object")
    if not isinstance(fixture, dict):
        return
    require(set(fixture) == INTAKE_EVAL_FIELDS, f"{label}: fields do not match contract")
    require(
        fixture.get("schema_version") == INTAKE_EVAL_SCHEMA_VERSION,
        f"{label}: wrong schema version",
    )
    require(
        fixture.get("evidence_kind") == "deterministic-contract-fixture",
        f"{label}: wrong evidence kind",
    )
    assurance_note = fixture.get("assurance_note")
    require(
        nonempty_string(assurance_note)
        and "not model-runtime evidence" in assurance_note
        and "not be reported as evaluated assurance" in assurance_note,
        f"{label}: assurance boundary is incomplete",
    )
    cases = fixture.get("cases")
    require(isinstance(cases, list) and bool(cases), f"{label}: cases must be non-empty")
    if not isinstance(cases, list):
        return

    seen_ids: set[str] = set()
    by_id: dict[str, dict[str, object]] = {}
    for case in cases:
        require(isinstance(case, dict), f"{label}: every case must be an object")
        if not isinstance(case, dict):
            continue
        require(set(case) == INTAKE_CASE_FIELDS, f"{label}: case fields do not match contract")
        case_id = case.get("id")
        require(
            isinstance(case_id, str) and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case_id)),
            f"{label}: invalid case ID",
        )
        if not isinstance(case_id, str) or not case_id:
            continue
        require(case_id not in seen_ids, f"{label}: duplicate case ID {case_id}")
        seen_ids.add(case_id)
        by_id[case_id] = case
        require(nonempty_string(case.get("prompt")), f"{label}/{case_id}: prompt must be non-empty")
        require(
            nonempty_string(case.get("expected_action")),
            f"{label}/{case_id}: expected_action must be non-empty",
        )
        expected_skill = case.get("expected_skill")
        require(
            expected_skill is None or expected_skill in manifests,
            f"{label}/{case_id}: expected_skill is unknown",
        )
        forbidden = case.get("forbidden_skills")
        require(
            isinstance(forbidden, list)
            and all(isinstance(item, str) and item in manifests for item in forbidden),
            f"{label}/{case_id}: forbidden_skills contains an unknown package",
        )
        if isinstance(forbidden, list):
            require(len(forbidden) == len(set(forbidden)), f"{label}/{case_id}: duplicate forbidden skill")
            require(expected_skill not in forbidden, f"{label}/{case_id}: expected skill is forbidden")

        question_count = case.get("expected_question_count_this_turn")
        first_decision = case.get("expected_first_decision_id")
        require(question_count in {0, 1}, f"{label}/{case_id}: question count must be 0 or 1")
        if question_count == 0:
            require(first_decision is None, f"{label}/{case_id}: zero-question case names a decision")
        elif question_count == 1:
            require(
                isinstance(expected_skill, str) and nonempty_string(first_decision),
                f"{label}/{case_id}: one-question case needs a Skill decision",
            )
            if isinstance(expected_skill, str) and expected_skill in manifests:
                intake = manifests[expected_skill].get("intake_contract")
                decisions = intake.get("decision_sequence") if isinstance(intake, dict) else None
                decision_ids = {
                    item.get("decision_id")
                    for item in decisions
                    if isinstance(item, dict)
                } if isinstance(decisions, list) else set()
                require(
                    first_decision in decision_ids,
                    f"{label}/{case_id}: first decision is absent from the Skill manifest",
                )

    require(len(cases) == expected_count, f"{label}: expected {expected_count} cases")
    for case_id, expected in required_oracles.items():
        case = by_id.get(case_id)
        require(case is not None, f"{label}: missing critical case {case_id}")
        if case is None:
            continue
        observed = (
            case.get("expected_skill"),
            case.get("expected_question_count_this_turn"),
            case.get("expected_first_decision_id"),
        )
        require(observed == expected, f"{label}/{case_id}: critical oracle differs")


def validate_intake_routing_cases(
    manifests: dict[str, dict[str, object]],
) -> None:
    fixture = load_json("evals/intake-routing-cases.json")
    validate_intake_routing_fixture(
        fixture,
        manifests,
        "intake routing fixture",
        expected_count=43,
        required_oracles=CRITICAL_INTAKE_CASES,
    )
    research_holdout = load_json(
        "evals/research-wave-r1-independent-routing-cases-v0.1.json"
    )
    validate_intake_routing_fixture(
        research_holdout,
        manifests,
        "research Wave R1 independent routing fixture",
        expected_count=6,
        required_oracles=RESEARCH_R1_HOLDOUT_ORACLES,
    )


def validate_template() -> None:
    template_path = ROOT / "templates/skill/SKILL.md.tmpl"
    template = template_path.read_text(encoding="utf-8")
    ordered_markers = [
        "Discover facts first.",
        "Ask only when necessary.",
        "Respect existing authorization.",
        "Confirm only new side effects.",
    ]
    positions = [template.find(marker) for marker in ordered_markers]
    require(all(position >= 0 for position in positions), "template: missing an intake state")
    require(positions == sorted(positions), "template: intake states are out of order")

    required_phrases = [
        "Safely inspect",
        "exactly one atomic question",
        "recommended answer",
        "proceed without a shared-understanding confirmation or a second execution confirmation",
        "not already explicitly authorized for the current action and scope",
        "provider-neutral",
        "advertising",
    ]
    for phrase in required_phrases:
        require(phrase in template, f"template: missing required contract phrase: {phrase}")

    manifest = load_json("templates/skill/manifest.json")
    require(isinstance(manifest, dict), "template manifest: expected an object")
    if isinstance(manifest, dict):
        validate_manifest_policy(manifest, "template manifest", allow_template_placeholders=True)
        frontmatter = read_frontmatter(template_path)
        validate_frontmatter(
            frontmatter,
            expected_name="replace-with-skill-name",
            expected_version=str(manifest.get("version", "")),
            label="template",
        )
    validate_apache_license(ROOT / "templates/skill/LICENSE", "template")


def validate_release_version() -> None:
    try:
        release_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        require(False, f"VERSION: unreadable: {exc}")
        return
    require(release_version == PUBLIC_PACKAGE_VERSION, "VERSION: wrong public release version")
    validate_apache_license(ROOT / "LICENSE", "repository")


def run_connector_self_test(root: Path = ROOT) -> None:
    script = root / "scripts/run_research_connector.py"
    safe_script = (
        script.is_file()
        and not script.is_symlink()
        and not script.parent.is_symlink()
        and script.resolve().is_relative_to(root.resolve())
    )
    require(
        safe_script,
        "connector runtime: shared executor must be a regular in-repository file",
    )
    if not safe_script:
        return
    try:
        completed = subprocess.run(
            [sys.executable, script.name, "--self-test"],
            cwd=script.parent,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        require(False, f"connector runtime: self-test could not complete: {exc}")
        return
    require(completed.returncode == 0, f"connector runtime: self-test exited {completed.returncode}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    require(bool(lines), "connector runtime: self-test produced no JSON result")
    if completed.returncode != 0 or not lines:
        return
    try:
        result = json_loads_no_duplicates(lines[-1])
    except (json.JSONDecodeError, DuplicateJSONKeyError):
        require(False, "connector runtime: self-test final output is not JSON")
        return
    require(isinstance(result, dict), "connector runtime: self-test result must be an object")
    if not isinstance(result, dict):
        return
    require(result.get("status") == "passed", "connector runtime: self-test did not pass")
    require(result.get("version") == PUBLIC_PACKAGE_VERSION, "connector runtime: version differs from release")
    require(result.get("network_performed") is False, "connector runtime: self-test unexpectedly used network")
    require(result.get("paid_use_authorized") is False, "connector runtime: self-test authorized paid use")


def package_code_files(package: Path) -> list[Path]:
    result: list[Path] = []
    for path in package.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(package)
        if any(part.startswith(".") for part in relative.parts):
            continue
        recognized_suffix = path.suffix.lower() in CODE_SUFFIXES
        in_scripts_directory = bool(relative.parts) and relative.parts[0] == "scripts"
        if recognized_suffix or in_scripts_directory:
            result.append(path)
    return sorted(result)


def package_symlinks(package: Path) -> list[Path]:
    if package.is_symlink():
        return [package]
    return sorted(path for path in package.rglob("*") if path.is_symlink())


def parse_script_self_test_output(stdout: str, expected_version: object, label: str) -> None:
    lines = [line for line in stdout.splitlines() if line.strip()]
    require(bool(lines), f"{label}: self-test produced no JSON result")
    if not lines:
        return
    try:
        result = json_loads_no_duplicates(lines[-1])
    except (json.JSONDecodeError, DuplicateJSONKeyError):
        require(False, f"{label}: self-test final output line is not JSON")
        return
    require(isinstance(result, dict), f"{label}: self-test result must be an object")
    if not isinstance(result, dict):
        return
    require(result.get("status") == "pass", f"{label}: self-test did not report pass")
    require(
        result.get("version") == expected_version,
        f"{label}: self-test version does not match manifest version",
    )


def run_script_self_test(
    package: Path,
    manifest: dict[str, object],
    label: str,
    code_files: list[Path],
) -> None:
    verification = manifest.get("script_verification")
    if not isinstance(verification, dict) or not code_files:
        return
    require(len(code_files) == 1, f"{label}: current manifest schema supports exactly one code artifact")
    if len(code_files) != 1:
        return
    raw_command = verification.get("self_test_command")
    if not isinstance(raw_command, str):
        return
    try:
        command = shlex.split(raw_command)
    except ValueError:
        require(False, f"{label}: self-test command cannot be parsed")
        return
    require(
        len(command) == 3
        and command[0] in {"python", "python3"}
        and command[2] == "--self-test",
        f"{label}: self-test command must be 'python3 scripts/<name>.py --self-test'",
    )
    if not (
        len(command) == 3
        and command[0] in {"python", "python3"}
        and command[2] == "--self-test"
    ):
        return
    relative_script = Path(command[1])
    require(
        not relative_script.is_absolute()
        and ".." not in relative_script.parts
        and len(relative_script.parts) >= 2
        and relative_script.parts[0] == "scripts"
        and relative_script.suffix.lower() == ".py",
        f"{label}: self-test must target a package Python script",
    )
    if not (
        not relative_script.is_absolute()
        and ".." not in relative_script.parts
        and len(relative_script.parts) >= 2
        and relative_script.parts[0] == "scripts"
        and relative_script.suffix.lower() == ".py"
    ):
        return
    script = package / relative_script
    expected_script = code_files[0]
    require(
        script == expected_script,
        f"{label}: self-test command must exactly cover the package code artifact",
    )
    require(
        script.is_file()
        and not script.is_symlink()
        and script.resolve().is_relative_to(package.resolve()),
        f"{label}: self-test script must be a regular in-package file",
    )
    if script != expected_script or not script.is_file() or script.is_symlink():
        return
    try:
        completed = subprocess.run(
            [sys.executable, relative_script.as_posix(), "--self-test"],
            cwd=package,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        require(False, f"{label}: self-test could not complete: {exc}")
        return
    require(completed.returncode == 0, f"{label}: self-test exited {completed.returncode}")
    if completed.returncode == 0:
        parse_script_self_test_output(completed.stdout, manifest.get("version"), label)


def allowed_package_relative(relative: Path) -> bool:
    return (
        not any(part.startswith(".") for part in relative.parts)
        and "__pycache__" not in relative.parts
        and relative.suffix != ".pyc"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_file_kind(relative: Path) -> str:
    upper_name = relative.name.upper()
    if upper_name.startswith(LEGAL_NOTICE_PREFIXES):
        return "license"
    if relative.as_posix() in {"manifest.json", "agents/interface.yaml"}:
        return "metadata"
    if (relative.parts and relative.parts[0] == "scripts") or relative.suffix.lower() in CODE_SUFFIXES:
        return "code"
    return "text"


def package_digest(package: Path) -> str:
    projection = []
    for path in sorted(item for item in package.rglob("*") if item.is_file()):
        relative = path.relative_to(package)
        if any(part.startswith(".") for part in relative.parts):
            continue
        projection.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_file(path),
                "kind": package_file_kind(relative),
            }
        )
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_preview_claims(package: Path, manifest: dict[str, object], label: str) -> None:
    if manifest.get("release_stage") != "preview":
        return
    for path in package.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".py", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in PREVIEW_POSITIVE_CLAIMS:
            require(not pattern.search(text), f"{label}: preview contains a validation or superiority claim in {path.relative_to(package)}")


def validate_external_service_boundary(
    package: Path,
    manifest: dict[str, object],
    label: str,
) -> None:
    external_services = manifest.get("external_services")
    if not isinstance(external_services, list) or not external_services:
        return
    boundary = package / "references/runtime-boundaries.md"
    require(boundary.is_file(), f"{label}: external service boundary document is missing")
    if not boundary.is_file():
        return
    lines = boundary.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("### External service gate") + 1
    except ValueError:
        require(False, f"{label}: external service gate section is missing")
        return
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("#")),
        len(lines),
    )
    fields: dict[str, str] = {}
    for line in lines[start:end]:
        match = re.fullmatch(r"- `([a-z_]+)`: `([a-z0-9_-]+)`", line.strip())
        if match:
            require(match.group(1) not in fields, f"{label}: duplicate external service boundary field")
            fields[match.group(1)] = match.group(2)
    require(
        fields == EXTERNAL_SERVICE_BOUNDARY_CONTRACT,
        f"{label}: external service boundary contract differs",
    )


def validate_installable_boundary() -> int:
    provider_ids = validate_connector_catalog()
    registry = load_json("registry.json")
    if not isinstance(registry, dict):
        require(False, "registry: expected an object")
        return 0
    require(registry.get("schema_version") == REGISTRY_SCHEMA_VERSION, "registry: wrong schema version")
    require(registry.get("policy") == "installable-packages-only", "registry: wrong policy")
    require(registry.get("lifecycle_axes") == REGISTRY_LIFECYCLE_AXES, "registry: lifecycle axes differ")
    entries = registry.get("skills")
    require(isinstance(entries, list), "registry: skills must be a list")
    if not isinstance(entries, list):
        return 0

    registry_entries: dict[str, dict[str, object]] = {}
    for entry in entries:
        require(isinstance(entry, dict), "registry: every entry must be an object")
        if not isinstance(entry, dict):
            continue
        required = {
            "manifest_schema_version",
            "name",
            "version",
            "path",
            "domain_id",
            "cluster_id",
            "status",
            "lifecycle_stage",
            "distribution_status",
            "release_stage",
            "assurance_level",
            "network_mode",
            "external_services",
            "package_digest",
            "previous_version",
        }
        require(required.issubset(entry), "registry: entry is missing a lifecycle field")
        name = entry.get("name")
        require(isinstance(name, str) and bool(name), "registry: every entry needs a name")
        if not isinstance(name, str) or not name:
            continue
        require(name not in registry_entries, f"registry: duplicate Skill {name}")
        registry_entries[name] = entry
        version = entry.get("version")
        domain_id = entry.get("domain_id")
        cluster_id = entry.get("cluster_id")
        digest = entry.get("package_digest")
        require(isinstance(version, str) and bool(SEMVER.fullmatch(version)), f"registry: invalid version for {name}")
        require(version == PUBLIC_PACKAGE_VERSION, f"registry: wrong release version for {name}")
        require(
            entry.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION,
            f"registry: wrong manifest schema version for {name}",
        )
        require(isinstance(domain_id, str) and bool(re.fullmatch(r"D[0-9]{2}", domain_id)), f"registry: invalid domain_id for {name}")
        require(isinstance(cluster_id, str) and bool(re.fullmatch(r"C[0-9]{2}", cluster_id)), f"registry: invalid cluster_id for {name}")
        require(isinstance(digest, str) and bool(SHA256.fullmatch(digest)), f"registry: invalid package_digest for {name}")
        previous = entry.get("previous_version")
        require(previous is None or (isinstance(previous, str) and bool(SEMVER.fullmatch(previous))), f"registry: invalid previous_version for {name}")
        release_stage = entry.get("release_stage")
        assurance_level = entry.get("assurance_level")
        require(
            isinstance(release_stage, str)
            and isinstance(assurance_level, str)
            and (release_stage, assurance_level) in ALLOWED_LIFECYCLES,
            f"registry: invalid lifecycle for {name}",
        )
        require(entry.get("path") == f"skills/{name}", f"registry: wrong package path for {name}")
        require(entry.get("status") == "active", f"registry: status must be active for {name}")
        require(
            entry.get("lifecycle_stage") == "production",
            f"registry: lifecycle_stage must be production for {name}",
        )
        require(
            entry.get("distribution_status") == "installable",
            f"registry: distribution_status must be installable for {name}",
        )
        network_mode = entry.get("network_mode")
        external_services = entry.get("external_services")
        require(network_mode in NETWORK_MODES, f"registry: invalid network_mode for {name}")
        require(nonempty_strings(external_services), f"registry: external_services must be a string list for {name}")
        if nonempty_strings(external_services):
            require(
                len(external_services) == len(set(external_services)),
                f"registry: duplicate external service for {name}",
            )
            require(
                set(external_services).issubset(provider_ids),
                f"registry: unknown external service for {name}",
            )
            if network_mode == "none":
                require(not external_services, f"registry: network_mode none has external services for {name}")
            else:
                require(bool(external_services), f"registry: networked package has no external service for {name}")

    package_names: set[str] = set()
    package_manifests: dict[str, dict[str, object]] = {}
    for package in sorted(
        path
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() or path.is_symlink()
    ):
        name = package.name
        package_names.add(name)
        symlinks = package_symlinks(package)
        for artifact in symlinks:
            relative = artifact.relative_to(package) if artifact != package else Path(".")
            require(
                False,
                f"skills/{name}: symlinks are forbidden: {relative}",
            )
        if symlinks:
            continue
        artifacts = list(package.rglob("*"))
        for artifact in artifacts:
            relative = artifact.relative_to(package)
            require(
                allowed_package_relative(relative),
                f"skills/{name}: hidden or cache package entry is forbidden: {relative}",
            )
        code_files = package_code_files(package)
        code_layout_ok = True
        if len(code_files) > 1:
            require(
                False,
                f"skills/{name}: current manifest schema supports at most one code artifact",
            )
            code_layout_ok = False
        for code_file in code_files:
            relative_code = code_file.relative_to(package)
            if (
                not relative_code.parts
                or relative_code.parts[0] != "scripts"
                or relative_code.suffix.lower() != ".py"
            ):
                require(
                    False,
                    f"skills/{name}: current manifest schema supports one Python artifact under scripts/",
                )
                code_layout_ok = False
        for relative in ("LICENSE", "SKILL.md", "manifest.json", "agents/interface.yaml"):
            require((package / relative).is_file(), f"skills/{name}: missing {relative}")
        if not (package / "SKILL.md").is_file() or not (package / "manifest.json").is_file():
            continue
        frontmatter = read_frontmatter(package / "SKILL.md")
        manifest = load_json(f"skills/{name}/manifest.json")
        if not isinstance(manifest, dict):
            continue
        package_manifests[name] = manifest
        validate_frontmatter(
            frontmatter,
            expected_name=name,
            expected_version=str(manifest.get("version", "")),
            label=f"skills/{name}",
        )
        require(manifest.get("name") == name, f"skills/{name}: manifest name mismatch")
        require(
            manifest.get("version") == PUBLIC_PACKAGE_VERSION,
            f"skills/{name}: wrong release version",
        )
        validate_manifest_policy(
            manifest,
            f"skills/{name} manifest",
            package=package,
            has_scripts=bool(code_files),
            provider_ids=provider_ids,
        )
        if code_layout_ok:
            run_script_self_test(package, manifest, f"skills/{name}", code_files)
        validate_external_service_boundary(package, manifest, f"skills/{name}")
        validate_preview_claims(package, manifest, f"skills/{name}")

        entry = registry_entries.get(name)
        require(entry is not None, f"skills/{name}: missing registry entry")
        if entry is not None:
            field_pairs = (
                ("manifest_schema_version", "schema_version"),
                ("version", "version"),
                ("domain_id", "domain_id"),
                ("cluster_id", "cluster_id"),
                ("status", "status"),
                ("lifecycle_stage", "lifecycle_stage"),
                ("distribution_status", "distribution_status"),
                ("release_stage", "release_stage"),
                ("assurance_level", "assurance_level"),
                ("network_mode", "network_mode"),
                ("external_services", "external_services"),
            )
            for registry_field, manifest_field in field_pairs:
                require(
                    entry.get(registry_field) == manifest.get(manifest_field),
                    f"skills/{name}: registry {registry_field} mismatch",
                )
            rollback = manifest.get("rollback")
            if isinstance(rollback, dict):
                require(entry.get("previous_version") == rollback.get("previous_version"), f"skills/{name}: registry previous_version mismatch")
            require(entry.get("package_digest") == package_digest(package), f"skills/{name}: registry package_digest mismatch")

    validate_dependency_references(package_manifests)
    validate_intake_routing_cases(package_manifests)
    require(package_names == set(registry_entries), "registry and complete Skill package names must match exactly")
    return len(package_names)


def validate_source_cleanliness(root: Path | None = None) -> None:
    scan_root = ROOT if root is None else root
    secret_patterns = (
        ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
        ("OpenAI API key", re.compile(r"\bsk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}\b")),
        ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
        (
            "PEM private key",
            re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
        ),
    )
    local_markers = ("/" + "Users/", "/" + "home/")
    obsolete_license_phrases = (
        "No outbound project " + "license has been selected",
        "does not yet declare an outbound " + "project license",
        "The repository is private during the " + "research phase",
    )
    paths: list[Path] = []
    for current, directories, filenames in os.walk(scan_root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for directory in directories:
            candidate = current_path / directory
            if directory in SOURCE_SCAN_EXCLUDED_DIRS:
                continue
            if candidate.is_symlink():
                paths.append(candidate)
            else:
                retained.append(directory)
        directories[:] = retained
        paths.extend(
            current_path / filename
            for filename in filenames
            if filename not in SOURCE_SCAN_EXCLUDED_DIRS
        )

    for path in sorted(paths):
        relative = path.relative_to(scan_root)
        if path.is_symlink():
            require(False, f"{relative}: repository symlinks are not allowed")
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            require(False, f"{relative}: source-clean scan could not read file: {exc}")
            continue
        for name, pattern in secret_patterns:
            require(not pattern.search(text), f"{relative}: possible {name}")
        require(not any(marker in text for marker in local_markers), f"{relative}: local absolute path")
        require(
            not any(phrase in text for phrase in obsolete_license_phrases),
            f"{relative}: obsolete outbound-license wording",
        )

    for path in sorted(
        path
        for path in paths
        if path.is_file() and not path.is_symlink() and path.suffix.lower() == ".py"
    ):
        relative = path.relative_to(scan_root)
        validate_spdx_header(path, relative.as_posix())


def captured_errors(action: object) -> list[str]:
    start = len(ERRORS)
    action()  # type: ignore[operator]
    result = ERRORS[start:]
    del ERRORS[start:]
    return result


def run_self_test() -> int:
    loaded_template = load_json("templates/skill/manifest.json")
    if not isinstance(loaded_template, dict):
        require(False, "self-test: template manifest could not be loaded")
        return 1
    template = loaded_template
    template.update(
        {
            "name": "example-skill",
            "domain_id": "D01",
            "cluster_id": "C01",
            "owner": "example-owner",
            "updated_at": "2026-08-08",
            "last_freshness_check": "2026-08-08",
        }
    )
    checks: list[str] = []

    try:
        json_loads_no_duplicates('{"outer":{"value":1,"value":2}}')
    except DuplicateJSONKeyError:
        pass
    else:
        require(False, "self-test: duplicate nested JSON key accepted")
    checks.append("duplicate-json-keys-rejected")

    intake_fixture = copy.deepcopy(template)
    intake_fixture["intake_contract"]["decision_sequence"] = [
        {
            "decision_id": "example-scope",
            "applies_when": "The requested comparison scope is absent or ambiguous.",
            "question": "Which comparison scope should be used?",
            "recommended_answer": "Use the smallest scope that answers the stated question.",
        }
    ]
    require(
        not captured_errors(
            lambda: validate_manifest_intake(intake_fixture, "specific-applies-when")
        ),
        "self-test: specific applies_when rejected",
    )
    for invalid_value in (None, "", GENERIC_APPLIES_WHEN):
        invalid_intake = copy.deepcopy(intake_fixture)
        invalid_intake["intake_contract"]["decision_sequence"][0]["applies_when"] = (
            invalid_value
        )
        require(
            bool(
                captured_errors(
                    lambda fixture=invalid_intake: validate_manifest_intake(
                        fixture, "invalid-applies-when"
                    )
                )
            ),
            "self-test: null, empty, or generic applies_when accepted",
        )
    checks.append("specific-applies-when-enforced")

    known_dependencies = {
        "alpha-skill": {"depends_on": ["beta-skill"]},
        "beta-skill": {"depends_on": []},
    }
    require(
        not captured_errors(
            lambda: validate_dependency_references(known_dependencies)
        ),
        "self-test: known dependency rejected",
    )
    unknown_dependency = copy.deepcopy(known_dependencies)
    unknown_dependency["alpha-skill"]["depends_on"] = ["missing-skill"]
    require(
        bool(
            captured_errors(
                lambda: validate_dependency_references(unknown_dependency)
            )
        ),
        "self-test: unknown dependency accepted",
    )
    self_dependency = copy.deepcopy(known_dependencies)
    self_dependency["alpha-skill"]["depends_on"] = ["alpha-skill"]
    require(
        bool(
            captured_errors(
                lambda: validate_dependency_references(self_dependency)
            )
        ),
        "self-test: self dependency accepted",
    )
    checks.append("dependency-references-checked")

    require(not captured_errors(lambda: validate_manifest_policy(template, "preview-reviewed")), "self-test: preview+reviewed rejected")
    checks.append("preview-reviewed-accepted")

    evaluated = copy.deepcopy(template)
    evaluated["assurance_level"] = "evaluated"
    evaluated["assurance"]["runtime_evaluation"] = "bounded-exact-package"
    evaluated["assurance"]["unverified_boundaries"] = [
        "scientific benchmark performance has not been established"
    ]
    evaluated["runtime_verification"] = {
        "mode": "bounded-exact-package",
        "status": "passed",
        "reason": None,
        "tool_versions": [],
        "unverified_boundaries": ["scientific benchmark performance has not been established"],
    }
    require(not captured_errors(lambda: validate_manifest_policy(evaluated, "preview-evaluated")), "self-test: preview+evaluated rejected")
    checks.append("preview-evaluated-accepted")

    stable = copy.deepcopy(evaluated)
    stable["release_stage"] = "stable"
    stable["rollback"]["previous_version"] = "0.0.9"
    require(not captured_errors(lambda: validate_manifest_policy(stable, "stable-evaluated")), "self-test: stable+evaluated rejected")
    checks.append("stable-evaluated-accepted")

    invalid_stable = copy.deepcopy(template)
    invalid_stable["release_stage"] = "stable"
    require(bool(captured_errors(lambda: validate_manifest_policy(invalid_stable, "stable-reviewed"))), "self-test: stable+reviewed accepted")
    checks.append("stable-reviewed-rejected")

    with tempfile.TemporaryDirectory(prefix="bio02-license-selftest-") as temp_name:
        package = Path(temp_name)
        license_path = package / "LICENSE"
        license_path.write_bytes((ROOT / "LICENSE").read_bytes())
        require(
            not captured_errors(
                lambda: validate_legal_notices(template, "valid-license", package)
            ),
            "self-test: canonical package LICENSE rejected",
        )
        license_path.unlink()
        require(
            bool(
                captured_errors(
                    lambda: validate_legal_notices(template, "missing-license", package)
                )
            ),
            "self-test: missing package LICENSE accepted",
        )
        license_path.write_text("not the Apache license\n", encoding="utf-8")
        require(
            bool(
                captured_errors(
                    lambda: validate_legal_notices(template, "changed-license", package)
                )
            ),
            "self-test: changed package LICENSE accepted",
        )
        bad_frontmatter: dict[str, object] = {
            "name": "example-skill",
            "description": "Example.",
            "license": "MIT",
            "metadata": {"version": template["version"]},
        }
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        bad_frontmatter,
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="wrong-license-frontmatter",
                    )
                )
            ),
            "self-test: wrong frontmatter license accepted",
        )
        bad_frontmatter["license"] = LICENSE_ID
        bad_frontmatter["metadata"] = {"version": "9.9.9"}
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        bad_frontmatter,
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="wrong-frontmatter-version",
                    )
                )
            ),
            "self-test: mismatched frontmatter version accepted",
        )
        long_name = "a" * 65
        long_name_frontmatter: dict[str, object] = {
            "name": long_name,
            "description": "Example.",
            "license": LICENSE_ID,
            "metadata": {"version": str(template["version"])},
        }
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        long_name_frontmatter,
                        expected_name=long_name,
                        expected_version=str(template["version"]),
                        label="long-frontmatter-name",
                    )
                )
            ),
            "self-test: overlong frontmatter name accepted",
        )
        python_path = package / "example.py"
        python_path.write_text("#!/usr/bin/env python3\nprint('example')\n", encoding="utf-8")
        require(
            bool(captured_errors(lambda: validate_spdx_header(python_path, "missing-spdx"))),
            "self-test: missing SPDX header accepted",
        )
        uppercase_python = package / "UPPER.PY"
        uppercase_python.write_text("print('example')\n", encoding="utf-8")
        require(
            uppercase_python in python_sources(package),
            "self-test: uppercase Python suffix escaped SPDX discovery",
        )
        require(
            bool(
                captured_errors(
                    lambda: validate_spdx_header(uppercase_python, "uppercase-missing-spdx")
                )
            ),
            "self-test: uppercase Python source without SPDX accepted",
        )
        malformed_quote = package / "malformed-quote.md"
        malformed_quote.write_text(
            "---\n"
            "name: example-skill\n"
            'description: "Example."\n'
            "license: 'Apache-2.0\"\n"
            "metadata:\n"
            f'  version: "{template["version"]}"\n'
            "---\n",
            encoding="utf-8",
        )
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        read_frontmatter(malformed_quote),
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="malformed-quote-frontmatter",
                    )
                )
            ),
            "self-test: malformed quoted frontmatter accepted",
        )
        block_scalar = package / "block-scalar.md"
        block_scalar.write_text(
            "---\n"
            "name: example-skill\n"
            "description: >\n"
            "license: Apache-2.0\n"
            "metadata:\n"
            f'  version: "{template["version"]}"\n'
            "---\n",
            encoding="utf-8",
        )
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        read_frontmatter(block_scalar),
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="block-scalar-frontmatter",
                    )
                )
            ),
            "self-test: unsupported block-scalar frontmatter accepted",
        )
        bare_line = package / "bare-line.md"
        bare_line.write_text(
            "---\n"
            "name: example-skill\n"
            'description: "Example."\n'
            "BROKEN\n"
            "license: Apache-2.0\n"
            "metadata:\n"
            f'  version: "{template["version"]}"\n'
            "---\n",
            encoding="utf-8",
        )
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        read_frontmatter(bare_line),
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="bare-line-frontmatter",
                    )
                )
            ),
            "self-test: malformed bare frontmatter line accepted",
        )
        implicit_null = package / "implicit-null.md"
        implicit_null.write_text(
            "---\n"
            "name: example-skill\n"
            "description: null\n"
            "license: Apache-2.0\n"
            "metadata:\n"
            f'  version: "{template["version"]}"\n'
            "---\n",
            encoding="utf-8",
        )
        require(
            bool(
                captured_errors(
                    lambda: validate_frontmatter(
                        read_frontmatter(implicit_null),
                        expected_name="example-skill",
                        expected_version=str(template["version"]),
                        label="implicit-null-frontmatter",
                    )
                )
            ),
            "self-test: YAML implicit null description accepted",
        )
    checks.append("apache-license-frontmatter-and-spdx-enforced")

    script = copy.deepcopy(template)
    script["script_verification"] = {
        "bundled_scripts": True,
        "implementation_origin": "original-rewrite-after-private-evaluation",
        "self_test_status": "passed",
        "self_test_command": "python3 scripts/example.py --self-test",
        "runtime_versions": ["Python 3.12"],
    }
    require(not captured_errors(lambda: validate_manifest_policy(script, "self-tested-script", has_scripts=True)), "self-test: valid script rejected")
    checks.append("self-tested-script-accepted")

    with tempfile.TemporaryDirectory(prefix="bio02-script-boundary-selftest-") as temp_name:
        test_root = Path(temp_name)
        symlink_package = test_root / "symlink-package"
        (symlink_package / "scripts").mkdir(parents=True)
        marker = test_root / "must-not-execute"
        outside = test_root / "outside.py"
        outside.write_text(
            "# SPDX-License-Identifier: Apache-2.0\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
            f"print('{{\"status\":\"pass\",\"version\":\"{PUBLIC_PACKAGE_VERSION}\"}}')\n",
            encoding="utf-8",
        )
        linked_script = symlink_package / "scripts/selftest.py"
        linked_script.symlink_to(outside)
        symlink_manifest = {
            "version": PUBLIC_PACKAGE_VERSION,
            "script_verification": {
                "self_test_command": "python3 scripts/selftest.py --self-test"
            },
        }
        symlink_errors = captured_errors(
            lambda: run_script_self_test(
                symlink_package,
                symlink_manifest,
                "symlink-script",
                [linked_script],
            )
        )
        require(bool(package_symlinks(symlink_package)), "self-test: package symlink was not discovered")
        require(bool(symlink_errors), "self-test: symlink self-test script was accepted")
        require(not marker.exists(), "self-test: symlink self-test script was executed")

        multi_package = test_root / "multi-package"
        (multi_package / "scripts").mkdir(parents=True)
        checked = multi_package / "scripts/checked.py"
        unchecked = multi_package / "scripts/unchecked.py"
        checked.write_text(
            "# SPDX-License-Identifier: Apache-2.0\n"
            f"print('{{\"status\":\"pass\",\"version\":\"{PUBLIC_PACKAGE_VERSION}\"}}')\n",
            encoding="utf-8",
        )
        unchecked.write_text(
            "# SPDX-License-Identifier: Apache-2.0\nraise RuntimeError('must not be ignored')\n",
            encoding="utf-8",
        )
        multi_manifest = {
            "version": PUBLIC_PACKAGE_VERSION,
            "script_verification": {
                "self_test_command": "python3 scripts/checked.py --self-test"
            },
        }
        require(
            bool(
                captured_errors(
                    lambda: run_script_self_test(
                        multi_package,
                        multi_manifest,
                        "multiple-code-artifacts",
                        [checked, unchecked],
                    )
                )
            ),
            "self-test: multiple code artifacts were accepted",
        )
        mismatched_manifest = copy.deepcopy(multi_manifest)
        mismatched_manifest["script_verification"]["self_test_command"] = (
            "python3 scripts/other.py --self-test"
        )
        require(
            bool(
                captured_errors(
                    lambda: run_script_self_test(
                        multi_package,
                        mismatched_manifest,
                        "uncovered-code-artifact",
                        [checked],
                    )
                )
            ),
            "self-test: command that did not cover the code artifact was accepted",
        )

        extensionless_package = test_root / "extensionless-package"
        (extensionless_package / "scripts").mkdir(parents=True)
        extensionless = extensionless_package / "scripts/runner"
        extensionless.write_text(
            "#!/usr/bin/env python3\n"
            "# SPDX-License-Identifier: Apache-2.0\n"
            f"print('{{\"status\":\"pass\",\"version\":\"{PUBLIC_PACKAGE_VERSION}\"}}')\n",
            encoding="utf-8",
        )
        extensionless.chmod(0o600)
        extensionless_code = package_code_files(extensionless_package)
        require(
            extensionless_code == [extensionless],
            "self-test: non-executable extensionless script escaped code discovery",
        )
        extensionless_manifest = {
            "version": PUBLIC_PACKAGE_VERSION,
            "script_verification": {
                "self_test_command": "python3 scripts/runner --self-test"
            },
        }
        require(
            bool(
                captured_errors(
                    lambda: run_script_self_test(
                        extensionless_package,
                        extensionless_manifest,
                        "unsupported-extensionless-code",
                        extensionless_code,
                    )
                )
            ),
            "self-test: executable extensionless code layout was accepted",
        )
    checks.append("script-file-boundary-enforced")

    with tempfile.TemporaryDirectory(prefix="bio02-source-clean-selftest-") as temp_name:
        source_root = Path(temp_name)
        (source_root / ".git").mkdir()
        (source_root / ".git/ignored").write_text(
            "ghp_" + "Z" * 24,
            encoding="utf-8",
        )
        (source_root / ".env").write_text(
            "OPENAI_KEY=" + "sk-" + "A" * 24 + "\n",
            encoding="utf-8",
        )
        (source_root / "UPPER.MD").write_text(
            "AWS_KEY=" + "AKIA" + "B" * 16 + "\n",
            encoding="utf-8",
        )
        (source_root / "extensionless").write_text(
            "-----BEGIN " + "PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        source_errors = captured_errors(
            lambda: validate_source_cleanliness(source_root)
        )
        require(
            len(source_errors) == 3,
            "self-test: hidden, uppercase, or extensionless secret scan differs",
        )
    checks.append("hidden-and-extensionless-secrets-rejected")

    require(
        not captured_errors(
            lambda: parse_script_self_test_output(
                f'{{"status":"pass","version":"{PUBLIC_PACKAGE_VERSION}"}}\n',
                PUBLIC_PACKAGE_VERSION,
                "matching-script-version",
            )
        ),
        "self-test: matching script version rejected",
    )
    require(
        bool(
            captured_errors(
                lambda: parse_script_self_test_output(
                    '{"status":"pass","version":"9.9.9"}\n',
                    PUBLIC_PACKAGE_VERSION,
                    "mismatched-script-version",
                )
            )
        ),
        "self-test: mismatched script version accepted",
    )
    checks.append("script-version-match-enforced")

    live_script_package = ROOT / "skills/statistical-analysis-and-multiple-testing"
    live_script_manifest = load_json(
        "skills/statistical-analysis-and-multiple-testing/manifest.json"
    )
    require(isinstance(live_script_manifest, dict), "self-test: live script manifest is invalid")
    if not isinstance(live_script_manifest, dict):
        return 1
    require(
        not captured_errors(
            lambda: run_script_self_test(
                live_script_package,
                live_script_manifest,
                "live-statistical-helper",
                package_code_files(live_script_package),
            )
        ),
        "self-test: live bundled-script self-test failed",
    )
    checks.append("live-bundled-script-self-test-passed")

    skipped_script = copy.deepcopy(script)
    skipped_script["script_verification"]["self_test_status"] = "skipped"
    skipped_script["script_verification"]["self_test_command"] = None
    require(bool(captured_errors(lambda: validate_manifest_policy(skipped_script, "skipped-small-script", has_scripts=True))), "self-test: skipped small script accepted")
    checks.append("skipped-small-script-rejected")

    complex_skip = copy.deepcopy(template)
    complex_skip["assurance"]["unverified_boundaries"].append("GPU batch path has not been run")
    complex_skip["runtime_verification"] = {
        "mode": "skipped-complex-tool",
        "status": "skipped",
        "reason": "GPU runtime is unavailable for this preview.",
        "tool_versions": ["example-tool 1.0"],
        "unverified_boundaries": ["GPU batch path has not been run"],
    }
    require(not captured_errors(lambda: validate_manifest_policy(complex_skip, "documented-complex-skip")), "self-test: documented complex skip rejected")
    checks.append("documented-complex-skip-accepted")

    bad_skip = copy.deepcopy(complex_skip)
    bad_skip["runtime_verification"]["reason"] = ""
    require(bool(captured_errors(lambda: validate_manifest_policy(bad_skip, "undocumented-complex-skip"))), "self-test: undocumented complex skip accepted")
    checks.append("undocumented-complex-skip-rejected")

    provider_ids = validate_connector_catalog()
    require(bool(provider_ids), "self-test: connector catalog was empty")
    with tempfile.TemporaryDirectory(prefix="bio02-connector-boundary-selftest-") as temp_name:
        test_root = Path(temp_name) / "repository"
        outside = Path(temp_name) / "outside"
        outside.mkdir()
        marker = Path(temp_name) / "must-not-execute"
        external_script = outside / "run_research_connector.py"
        external_script.write_text(
            "# SPDX-License-Identifier: Apache-2.0\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
            f"print('{{\"status\":\"passed\",\"version\":\"{PUBLIC_PACKAGE_VERSION}\"}}')\n",
            encoding="utf-8",
        )
        test_root.mkdir()
        (test_root / "scripts").symlink_to(outside, target_is_directory=True)
        require(
            bool(captured_errors(lambda: run_connector_self_test(test_root))),
            "self-test: symlinked shared connector was accepted",
        )
        require(not marker.exists(), "self-test: symlinked shared connector was executed")
    checks.append("connector-runtime-boundary-enforced")
    require(
        not captured_errors(run_connector_self_test),
        "self-test: shared connector runtime self-test failed",
    )
    connector_manifest = copy.deepcopy(template)
    connector_manifest["network_mode"] = "optional"
    connector_manifest["external_services"] = ["ncbi-eutils"]
    require(
        not captured_errors(
            lambda: validate_manifest_policy(
                connector_manifest,
                "known-connector-reference",
                provider_ids=provider_ids,
            )
        ),
        "self-test: known connector reference rejected",
    )
    unknown_connector = copy.deepcopy(connector_manifest)
    unknown_connector["external_services"] = ["not-in-catalog"]
    require(
        bool(
            captured_errors(
                lambda: validate_manifest_policy(
                    unknown_connector,
                    "unknown-connector-reference",
                    provider_ids=provider_ids,
                )
            )
        ),
        "self-test: unknown connector reference accepted",
    )
    checks.append("connector-catalog-and-references-checked")
    checks.append("connector-runtime-self-test-passed")

    intake_manifests: dict[str, dict[str, object]] = {}
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.json")):
        decoded = json_loads_no_duplicates(manifest_path.read_text(encoding="utf-8"))
        if isinstance(decoded, dict) and isinstance(decoded.get("name"), str):
            intake_manifests[decoded["name"]] = decoded
    intake_fixture = json_loads_no_duplicates(
        (ROOT / "evals/intake-routing-cases.json").read_text(encoding="utf-8")
    )
    require(
        not captured_errors(
            lambda: validate_intake_routing_fixture(
                intake_fixture,
                intake_manifests,
                "self-test intake fixture",
                expected_count=43,
                required_oracles=CRITICAL_INTAKE_CASES,
            )
        ),
        "self-test: valid intake routing fixture rejected",
    )
    invalid_intake_fixture = copy.deepcopy(intake_fixture)
    if isinstance(invalid_intake_fixture, dict):
        invalid_cases = invalid_intake_fixture.get("cases")
        if isinstance(invalid_cases, list):
            for case in invalid_cases:
                if isinstance(case, dict) and case.get("id") == "vcf-missing-reference-first":
                    case["expected_first_decision_id"] = "not-a-real-decision"
                    break
    require(
        bool(
            captured_errors(
                lambda: validate_intake_routing_fixture(
                    invalid_intake_fixture,
                    intake_manifests,
                    "self-test invalid intake fixture",
                    expected_count=43,
                    required_oracles=CRITICAL_INTAKE_CASES,
                )
            )
        ),
        "self-test: invalid intake routing oracle accepted",
    )
    checks.append("intake-routing-fixture-enforced")

    research_holdout = json_loads_no_duplicates(
        (ROOT / "evals/research-wave-r1-independent-routing-cases-v0.1.json").read_text(
            encoding="utf-8"
        )
    )
    require(
        not captured_errors(
            lambda: validate_intake_routing_fixture(
                research_holdout,
                intake_manifests,
                "self-test research Wave R1 holdout",
                expected_count=6,
                required_oracles=RESEARCH_R1_HOLDOUT_ORACLES,
            )
        ),
        "self-test: valid research Wave R1 holdout rejected",
    )
    invalid_research_holdout = copy.deepcopy(research_holdout)
    if isinstance(invalid_research_holdout, dict):
        invalid_cases = invalid_research_holdout.get("cases")
        if isinstance(invalid_cases, list):
            for case in invalid_cases:
                if isinstance(case, dict) and case.get("id") == "contacts-r1-blind-positive":
                    case["expected_skill"] = "protein-structure-retrieval-and-comparison"
                    break
    require(
        bool(
            captured_errors(
                lambda: validate_intake_routing_fixture(
                    invalid_research_holdout,
                    intake_manifests,
                    "self-test invalid research Wave R1 holdout",
                    expected_count=6,
                    required_oracles=RESEARCH_R1_HOLDOUT_ORACLES,
                )
            )
        ),
        "self-test: invalid research Wave R1 holdout oracle accepted",
    )
    checks.append("research-wave-r1-routing-holdout-enforced")

    preview_disclaimer = "This preview is not scientifically validated."
    positive_claim = "This preview is scientifically validated."
    require(not any(pattern.search(preview_disclaimer) for pattern in PREVIEW_POSITIVE_CLAIMS), "self-test: negated preview disclaimer rejected")
    require(any(pattern.search(positive_claim) for pattern in PREVIEW_POSITIVE_CLAIMS), "self-test: positive validation claim accepted")
    checks.append("preview-claim-negation-handled")

    require(not allowed_package_relative(Path(".env")), "self-test: hidden package file accepted")
    require(not allowed_package_relative(Path("scripts/__pycache__/tool.pyc")), "self-test: cache package file accepted")
    require(allowed_package_relative(Path("scripts/tool.py")), "self-test: ordinary package file rejected")
    checks.append("hidden-and-cache-files-rejected")

    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}")
        return 1
    print(json.dumps({"status": "pass", "validator": VALIDATOR_VERSION, "checks": checks}, sort_keys=True))
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        return run_self_test()
    if sys.argv[1:]:
        print("usage: validate_skeleton.py [--self-test]", file=sys.stderr)
        return 2

    validate_release_version()
    run_connector_self_test()
    validate_template()
    installable_packages = validate_installable_boundary()
    validate_source_cleanliness()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}")
        return 1
    print(
        "02-bio-skills skeleton: ok"
        f" | validator={VALIDATOR_VERSION}"
        f" intake={INTAKE_CONTRACT_VERSION}"
        f" installable_packages={installable_packages}"
        " source_clean=ok"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
