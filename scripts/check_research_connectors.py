#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Disclosure-first, zero-network doctor for optional research connectors."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, TextIO


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "connectors" / "providers.json"
CONFIG_SCHEMA_VERSION = "0.1.0"
MAX_CONFIG_BYTES = 64 * 1024
ENV_NAME = re.compile(r"^BIO02_[A-Z][A-Z0-9_]{0,120}$")
HOST_NAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

EXPECTED_PROVIDER_IDS = (
    "ncbi-eutils",
    "europe-pmc",
    "openalex",
    "ebi-biostudies",
    "rcsb-pdb",
    "alphafold-db",
    "pubchem-pug-rest",
    "chembl-rest",
    "crossref-rest",
    "quickgo",
    "enrichr",
    "kegg-rest",
    "embl-ebi-job-dispatcher",
    "ncbi-blast-remote",
)

CATALOG_FIELDS = {
    "schema_version",
    "mode",
    "freshness_checked_at",
    "provider_ids",
    "providers",
}
PROVIDER_FIELDS = {
    "display_name",
    "purpose",
    "would_send",
    "credential_fields",
    "billing",
    "allowed_hosts",
    "official_docs",
}
CREDENTIAL_FIELDS = {"name", "kind", "requirement"}
BILLING_FIELDS = {
    "mode",
    "requires_separate_paid_authorization",
    "summary",
}
CONFIG_FIELDS = {"schema_version", "providers"}
CONFIG_PROVIDER_FIELDS = {"enabled", "credential_env"}


class ValidationError(ValueError):
    """A catalog or user-configuration boundary was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(nonempty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, *, max_bytes: int | None = None) -> object:
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            raise ValidationError(f"JSON file exceeds {max_bytes} bytes")
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except ValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"unreadable or invalid JSON: {exc}") from exc


def validate_catalog(catalog: object) -> dict[str, object]:
    require(isinstance(catalog, dict), "catalog must be a JSON object")
    assert isinstance(catalog, dict)
    require(set(catalog) == CATALOG_FIELDS, "catalog fields do not match the connector contract")
    require(catalog.get("schema_version") == CONFIG_SCHEMA_VERSION, "unsupported catalog schema_version")
    require(catalog.get("mode") == "plan-only", "catalog mode must be plan-only")
    require(nonempty_string(catalog.get("freshness_checked_at")), "catalog freshness date is required")

    provider_ids = catalog.get("provider_ids")
    require(
        isinstance(provider_ids, list) and tuple(provider_ids) == EXPECTED_PROVIDER_IDS,
        "catalog provider_ids differ from the frozen allowlist",
    )
    providers = catalog.get("providers")
    require(isinstance(providers, dict), "catalog providers must be an object")
    assert isinstance(providers, dict)
    require(tuple(providers) == EXPECTED_PROVIDER_IDS, "catalog provider keys differ from the frozen allowlist")

    for provider_id, provider in providers.items():
        label = f"provider {provider_id}"
        require(isinstance(provider, dict), f"{label} must be an object")
        assert isinstance(provider, dict)
        require(set(provider) == PROVIDER_FIELDS, f"{label} fields do not match the connector contract")
        require(nonempty_string(provider.get("display_name")), f"{label} display_name is required")
        require(nonempty_string(provider.get("purpose")), f"{label} purpose is required")
        require(string_list(provider.get("would_send")), f"{label} would_send must be a unique string list")

        credential_fields = provider.get("credential_fields")
        require(isinstance(credential_fields, list), f"{label} credential_fields must be a list")
        credential_names: list[str] = []
        for field in credential_fields:
            require(isinstance(field, dict), f"{label} credential field must be an object")
            assert isinstance(field, dict)
            require(set(field) == CREDENTIAL_FIELDS, f"{label} credential field shape is invalid")
            name = field.get("name")
            require(
                isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None,
                f"{label} credential name is invalid",
            )
            credential_names.append(name)
            require(field.get("kind") in {"contact", "secret"}, f"{label} credential kind is invalid")
            require(
                field.get("requirement") in {"required", "optional"},
                f"{label} credential requirement is invalid",
            )
        require(
            len(credential_names) == len(set(credential_names)),
            f"{label} credential names must be unique",
        )

        billing = provider.get("billing")
        require(isinstance(billing, dict), f"{label} billing must be an object")
        assert isinstance(billing, dict)
        require(set(billing) == BILLING_FIELDS, f"{label} billing shape is invalid")
        require(
            billing.get("mode") in {"public-free", "metered", "mixed", "terms-restricted"},
            f"{label} billing mode is invalid",
        )
        require(
            isinstance(billing.get("requires_separate_paid_authorization"), bool),
            f"{label} paid-authorization flag must be boolean",
        )
        require(nonempty_string(billing.get("summary")), f"{label} billing summary is required")

        allowed_hosts = provider.get("allowed_hosts")
        require(string_list(allowed_hosts), f"{label} allowed_hosts must be a unique string list")
        assert isinstance(allowed_hosts, list)
        require(
            all(HOST_NAME.fullmatch(host) is not None for host in allowed_hosts),
            f"{label} allowed_hosts contains a non-host value",
        )
        official_docs = provider.get("official_docs")
        require(
            isinstance(official_docs, str) and official_docs.startswith("https://"),
            f"{label} official_docs must be an HTTPS URL",
        )
    return catalog


def load_catalog() -> dict[str, object]:
    return validate_catalog(read_json(CATALOG_PATH))


def validate_config(config: object, catalog: dict[str, object]) -> dict[str, object]:
    require(isinstance(config, dict), "configuration must be a JSON object")
    assert isinstance(config, dict)
    require(set(config) == CONFIG_FIELDS, "configuration fields do not match the connector contract")
    require(config.get("schema_version") == CONFIG_SCHEMA_VERSION, "unsupported configuration schema_version")
    providers = config.get("providers")
    require(isinstance(providers, dict), "configuration providers must be an object")
    assert isinstance(providers, dict)

    catalog_providers = catalog["providers"]
    assert isinstance(catalog_providers, dict)
    unknown = sorted(set(providers) - set(catalog_providers))
    require(not unknown, "configuration contains unknown provider IDs")

    for provider_id, entry in providers.items():
        label = f"configuration provider {provider_id}"
        require(isinstance(entry, dict), f"{label} must be an object")
        assert isinstance(entry, dict)
        require(set(entry) == CONFIG_PROVIDER_FIELDS, f"{label} fields do not match the connector contract")
        require(isinstance(entry.get("enabled"), bool), f"{label} enabled must be boolean")
        credential_env = entry.get("credential_env")
        require(isinstance(credential_env, dict), f"{label} credential_env must be an object")
        assert isinstance(credential_env, dict)

        catalog_entry = catalog_providers[provider_id]
        assert isinstance(catalog_entry, dict)
        definitions = catalog_entry["credential_fields"]
        assert isinstance(definitions, list)
        allowed_names = {field["name"] for field in definitions}
        unknown_names = sorted(set(credential_env) - allowed_names)
        require(
            not unknown_names,
            f"{label} contains unsupported credential fields",
        )
        for field_name, env_name in credential_env.items():
            require(
                isinstance(env_name, str) and ENV_NAME.fullmatch(env_name) is not None,
                f"{label} {field_name} must be a BIO02_-prefixed environment-variable name",
            )
        require(
            len(credential_env.values()) == len(set(credential_env.values())),
            f"{label} must not reuse one environment variable for different fields",
        )
    return config


def disclosure(provider_id: str, provider: dict[str, object]) -> dict[str, object]:
    billing = provider["billing"]
    assert isinstance(billing, dict)
    return {
        "event": "disclosure",
        "provider_id": provider_id,
        "purpose": provider["purpose"],
        "would_send": provider["would_send"],
        "credential_requirements": provider["credential_fields"],
        "billing": provider["billing"],
        "paid_use_authorized": False,
        "separate_paid_authorization_required": billing[
            "requires_separate_paid_authorization"
        ],
        "allowed_hosts": provider["allowed_hosts"],
        "plan_output": "stdout-jsonl",
        "remote_output": "none",
        "execution_mode": "plan-only",
        "config_read": False,
        "live_ready": False,
        "network_performed": False,
    }


def confirmation_token(
    provider_ids: list[str],
    catalog: dict[str, object],
) -> str:
    providers = catalog["providers"]
    assert isinstance(providers, dict)
    payload = {
        "contract": "bio02-research-connectors-confirmation-v1",
        "catalog_schema_version": catalog["schema_version"],
        "catalog_freshness_checked_at": catalog["freshness_checked_at"],
        "disclosures": [
            disclosure(provider_id, providers[provider_id])
            for provider_id in provider_ids
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"bio02-ack-v1-{hashlib.sha256(canonical).hexdigest()}"


def plan_provider(
    provider_id: str,
    provider: dict[str, object],
    config: dict[str, object] | None,
    environ: Mapping[str, str],
) -> dict[str, object]:
    base: dict[str, object] = {
        "event": "plan",
        "provider_id": provider_id,
        "config_read": config is not None,
        "execution_available": False,
        "live_ready": False,
        "network_performed": False,
    }
    if config is None:
        return {**base, "status": "needs-user-config", "reason": "configuration file is required"}

    configured_providers = config["providers"]
    assert isinstance(configured_providers, dict)
    entry = configured_providers.get(provider_id)
    if not isinstance(entry, dict):
        return {**base, "status": "needs-user-config", "reason": "provider is absent from configuration"}
    if entry.get("enabled") is not True:
        return {**base, "status": "needs-user-config", "reason": "provider is disabled in configuration"}

    credential_env = entry["credential_env"]
    assert isinstance(credential_env, dict)
    definitions = provider["credential_fields"]
    assert isinstance(definitions, list)
    credential_status: list[dict[str, object]] = []
    required_mapping_missing = False
    required_value_missing = False
    for definition in definitions:
        assert isinstance(definition, dict)
        name = definition["name"]
        requirement = definition["requirement"]
        assert isinstance(name, str)
        env_name = credential_env.get(name)
        if not isinstance(env_name, str):
            status = "not-configured"
            if requirement == "required":
                required_mapping_missing = True
        elif not environ.get(env_name):
            status = "missing"
            if requirement == "required":
                required_value_missing = True
        else:
            status = "available"
        credential_status.append(
            {
                "name": name,
                "kind": definition["kind"],
                "requirement": requirement,
                "environment_variable_configured": isinstance(env_name, str),
                "status": status,
            }
        )

    if required_mapping_missing:
        status = "needs-user-config"
        reason = "required credential environment-variable names are not configured"
    elif required_value_missing:
        status = "needs-credential"
        reason = "required named environment variables are not set"
    else:
        status = "config-validated"
        reason = "configuration references are valid; no live adapter was executed or evaluated"

    billing = provider["billing"]
    assert isinstance(billing, dict)
    return {
        **base,
        "status": status,
        "reason": reason,
        "credentials": credential_status,
        "paid_use_authorized": False,
        "separate_paid_authorization_required": billing["requires_separate_paid_authorization"],
    }


def emit(out: TextIO, event: dict[str, object]) -> None:
    event.setdefault("live_ready", False)
    event.setdefault("paid_use_authorized", False)
    event.setdefault("network_performed", False)
    print(json.dumps(event, ensure_ascii=False, sort_keys=True), file=out, flush=True)


def summary_status(plans: list[dict[str, object]]) -> tuple[str, int]:
    statuses = {plan["status"] for plan in plans}
    if "needs-user-config" in statuses:
        return "needs-user-config", 2
    if "needs-credential" in statuses:
        return "needs-credential", 4
    return "config-validated", 0


def load_user_config(
    config_path: Path,
    catalog: dict[str, object],
) -> dict[str, object] | None:
    if not config_path.is_file():
        return None
    return validate_config(read_json(config_path, max_bytes=MAX_CONFIG_BYTES), catalog)


def execute_plan(
    provider_ids: list[str],
    config_path: Path | None,
    acknowledge: str | None,
    catalog: dict[str, object],
    environ: Mapping[str, str],
    out: TextIO,
    config_loader: Callable[
        [Path, dict[str, object]], dict[str, object] | None
    ] = load_user_config,
) -> int:
    providers = catalog["providers"]
    assert isinstance(providers, dict)

    # Disclosure is deliberately emitted and flushed before user config is touched.
    for provider_id in provider_ids:
        provider = providers[provider_id]
        assert isinstance(provider, dict)
        emit(out, disclosure(provider_id, provider))

    token = confirmation_token(provider_ids, catalog)
    if acknowledge != token:
        emit(
            out,
            {
                "event": "confirmation",
                "status": "needs-user-confirmation",
                "confirmation_token": token,
                "acknowledgement_matches": False,
                "config_read": False,
                "execution_available": False,
                "live_ready": False,
                "paid_use_authorized": False,
                "network_performed": False,
            },
        )
        return 5

    emit(
        out,
        {
            "event": "confirmation",
            "status": "acknowledged",
            "confirmation_token": token,
            "acknowledgement_matches": True,
            "config_read": False,
            "execution_available": False,
            "live_ready": False,
            "paid_use_authorized": False,
            "network_performed": False,
        },
    )

    config: dict[str, object] | None = None
    if config_path is not None:
        try:
            config = config_loader(config_path, catalog)
        except ValidationError as exc:
            emit(
                out,
                {
                    "event": "error",
                    "status": "invalid-config",
                    "reason": str(exc),
                    "config_read": True,
                    "live_ready": False,
                    "paid_use_authorized": False,
                    "network_performed": False,
                },
            )
            return 3

    plans: list[dict[str, object]] = []
    for provider_id in provider_ids:
        provider = providers[provider_id]
        assert isinstance(provider, dict)
        plan = plan_provider(provider_id, provider, config, environ)
        plans.append(plan)
        emit(out, plan)
    status, exit_code = summary_status(plans)
    emit(
        out,
        {
            "event": "summary",
            "status": status,
            "providers": provider_ids,
            "execution_available": False,
            "live_ready": False,
            "paid_use_authorized": False,
            "network_performed": False,
        },
    )
    return exit_code


def selected_provider_ids(
    requested: list[str] | None,
    use_all: bool,
    catalog: dict[str, object],
) -> list[str]:
    require(bool(requested) != use_all, "select --provider at least once or use --all")
    if use_all:
        return list(EXPECTED_PROVIDER_IDS)
    assert requested is not None
    require(len(requested) == len(set(requested)), "provider IDs must not be repeated")
    providers = catalog["providers"]
    assert isinstance(providers, dict)
    unknown = sorted(set(requested) - set(providers))
    require(not unknown, "unknown provider IDs are not allowed")
    return requested


def self_test(catalog: dict[str, object]) -> int:
    import ast

    checks = 0
    require(tuple(catalog["provider_ids"]) == EXPECTED_PROVIDER_IDS, "frozen provider allowlist changed")
    checks += 1

    output = io.StringIO()
    exit_code = execute_plan(["openalex"], None, None, catalog, {}, output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    require(exit_code == 5, "unacknowledged disclosure must exit 5")
    require([event["event"] for event in events] == ["disclosure", "confirmation"], "disclosure order changed")
    require(events[0]["config_read"] is False, "disclosure must precede configuration read")
    require(
        events[0]["plan_output"] == "stdout-jsonl"
        and events[0]["remote_output"] == "none",
        "disclosure must identify the only output boundary",
    )
    require(events[1]["status"] == "needs-user-confirmation", "confirmation status changed")
    checks += 1

    token = confirmation_token(["openalex"], catalog)
    require(
        token == confirmation_token(["openalex"], catalog),
        "confirmation token must be deterministic",
    )
    output = io.StringIO()
    require(
        execute_plan(["openalex"], None, token, catalog, {}, output) == 2,
        "acknowledged missing configuration must exit 2",
    )
    checks += 1

    with tempfile.TemporaryDirectory(prefix="bio02-connectors-self-test-") as temp_dir:
        temp_root = Path(temp_dir)
        malicious_config = temp_root / "must-not-read.json"
        malicious_config.write_text('{"api_key":"literal-secret"}', encoding="utf-8")
        before_mtime = malicious_config.stat().st_mtime_ns
        loader_calls = 0

        def forbidden_loader(
            _path: Path,
            _catalog: dict[str, object],
        ) -> dict[str, object] | None:
            nonlocal loader_calls
            loader_calls += 1
            raise ValidationError("unacknowledged configuration was read")

        for supplied_ack in (None, "wrong-token"):
            output = io.StringIO()
            require(
                execute_plan(
                    ["openalex"],
                    malicious_config,
                    supplied_ack,
                    catalog,
                    {},
                    output,
                    forbidden_loader,
                )
                == 5,
                "missing or wrong acknowledgement must exit 5",
            )
        require(loader_calls == 0, "wrong acknowledgement touched the config loader")
        require(
            malicious_config.stat().st_mtime_ns == before_mtime,
            "unacknowledged config mtime changed",
        )
        checks += 1

        class UntouchableConfigPath:
            def __init__(self) -> None:
                self.touches = 0

            def __getattribute__(self, name: str) -> object:
                if name == "touches":
                    return object.__getattribute__(self, name)
                object.__setattr__(
                    self,
                    "touches",
                    object.__getattribute__(self, "touches") + 1,
                )
                raise AssertionError(f"config path was touched through {name}")

        path_probe = UntouchableConfigPath()
        output = io.StringIO()
        require(
            execute_plan(
                ["openalex"],
                path_probe,  # type: ignore[arg-type]
                None,
                catalog,
                {},
                output,
            )
            == 5,
            "unacknowledged path probe must exit 5",
        )
        require(path_probe.touches == 0, "unacknowledged config path was stat/open/read")
        checks += 1

        public_config = temp_root / "public.json"
        public_config.write_text(
            json.dumps(
                {
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "providers": {
                        "europe-pmc": {"enabled": True, "credential_env": {}}
                    },
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        require(
            execute_plan(
                ["europe-pmc"],
                public_config,
                confirmation_token(["europe-pmc"], catalog),
                catalog,
                {},
                output,
            )
            == 0,
            "credential-free configured provider must validate",
        )
        checks += 1

        credential_config = temp_root / "credential.json"
        credential_config.write_text(
            json.dumps(
                {
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "providers": {
                        "openalex": {
                            "enabled": True,
                            "credential_env": {"api_key": "BIO02_TEST_OPENALEX_API_KEY"},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        require(
            execute_plan(
                ["openalex"], credential_config, token, catalog, {}, output
            )
            == 4,
            "unset required environment variable must exit 4",
        )
        checks += 1

        secret_value = "SECRET_VALUE_MUST_NOT_BE_PRINTED"
        output = io.StringIO()
        require(
            execute_plan(
                ["openalex"],
                credential_config,
                token,
                catalog,
                {"BIO02_TEST_OPENALEX_API_KEY": secret_value},
                output,
            )
            == 0,
            "set required environment variable must validate",
        )
        require(secret_value not in output.getvalue(), "credential value leaked to output")
        checks += 1

        literal_secret = temp_root / "literal-secret.json"
        literal_secret.write_text(
            json.dumps(
                {
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "providers": {
                        "openalex": {
                            "enabled": True,
                            "credential_env": {"api_key": "sk-direct-secret"},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        require(
            execute_plan(
                ["openalex"], literal_secret, token, catalog, {}, output
            )
            == 3,
            "literal-looking secret must fail environment-name validation",
        )
        require(json.loads(output.getvalue().splitlines()[0])["event"] == "disclosure", "invalid config was read before disclosure")
        checks += 1

        uppercase_literal = temp_root / "uppercase-literal.json"
        uppercase_secret = "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        uppercase_literal.write_text(
            json.dumps(
                {
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "providers": {
                        "openalex": {
                            "enabled": True,
                            "credential_env": {"api_key": uppercase_secret},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        require(
            execute_plan(
                ["openalex"], uppercase_literal, token, catalog, {}, output
            )
            == 3,
            "uppercase literal without BIO02_ prefix must fail validation",
        )
        require(uppercase_secret not in output.getvalue(), "literal credential leaked to output")
        checks += 1

        unknown_key_config = temp_root / "unknown-key.json"
        unknown_secret = "UNKNOWN_PROVIDER_SECRET_MUST_NOT_ECHO"
        unknown_key_config.write_text(
            json.dumps(
                {
                    "schema_version": CONFIG_SCHEMA_VERSION,
                    "providers": {
                        unknown_secret: {"enabled": True, "credential_env": {}}
                    },
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        require(
            execute_plan(
                ["europe-pmc"],
                unknown_key_config,
                confirmation_token(["europe-pmc"], catalog),
                catalog,
                {},
                output,
            )
            == 3,
            "unknown provider key must fail validation",
        )
        require(unknown_secret not in output.getvalue(), "unknown key leaked to output")
        checks += 1

    try:
        selected_provider_ids(["not-a-provider"], False, catalog)
    except ValidationError:
        pass
    else:
        raise ValidationError("unknown provider did not fail closed")
    checks += 1

    source_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(source_tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    require(
        imported_roots.isdisjoint({"http", "requests", "socket", "urllib"}),
        "doctor must not import a network client",
    )
    checks += 1

    print(
        json.dumps(
            {
                "event": "self-test",
                "status": "passed",
                "checks": checks,
                "providers": len(EXPECTED_PROVIDER_IDS),
                "live_ready": False,
                "paid_use_authorized": False,
                "network_performed": False,
            },
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Disclose and validate a zero-network research-connector plan."
    )
    parser.add_argument(
        "--provider",
        action="append",
        help="Canonical provider ID; repeat for multiple providers.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Plan every provider in the frozen allowlist.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="User JSON containing provider enablement and environment-variable names only.",
    )
    parser.add_argument(
        "--acknowledge",
        help="Exact confirmation token emitted by a prior disclosure-only run.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic zero-network boundary checks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        catalog = load_catalog()
        if args.self_test:
            require(
                not args.provider
                and not args.all
                and args.config is None
                and args.acknowledge is None,
                "--self-test cannot be combined with planning arguments",
            )
            return self_test(catalog)
        provider_ids = selected_provider_ids(args.provider, args.all, catalog)
        return execute_plan(
            provider_ids,
            args.config,
            args.acknowledge,
            catalog,
            os.environ,
            sys.stdout,
        )
    except ValidationError as exc:
        emit(
            sys.stdout,
            {
                "event": "error",
                "status": "invalid-request",
                "reason": str(exc),
                "network_performed": False,
            },
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
