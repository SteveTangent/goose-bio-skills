#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render or check registry entries from package manifests and exact bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import validate_skeleton as contracts


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "registry.json"


class RegistryError(ValueError):
    """The registry cannot be rendered or differs from package truth."""


def strict_object(path: Path) -> dict[str, Any]:
    try:
        value = contracts.json_loads_no_duplicates(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, contracts.DuplicateJSONKeyError) as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"expected JSON object: {path}")
    return value


def entry_from_package(package: Path) -> dict[str, Any]:
    manifest = strict_object(package / "manifest.json")
    rollback = manifest.get("rollback")
    if not isinstance(rollback, dict):
        raise RegistryError(f"rollback object is missing: {package.name}")
    return {
        "manifest_schema_version": manifest.get("schema_version"),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "path": f"skills/{package.name}",
        "domain_id": manifest.get("domain_id"),
        "cluster_id": manifest.get("cluster_id"),
        "status": manifest.get("status"),
        "lifecycle_stage": manifest.get("lifecycle_stage"),
        "distribution_status": manifest.get("distribution_status"),
        "release_stage": manifest.get("release_stage"),
        "assurance_level": manifest.get("assurance_level"),
        "network_mode": manifest.get("network_mode"),
        "external_services": manifest.get("external_services"),
        "package_digest": contracts.package_digest(package),
        "previous_version": rollback.get("previous_version"),
    }


def render() -> dict[str, Any]:
    current = strict_object(REGISTRY_PATH)
    skills_root = ROOT / "skills"
    packages = sorted(
        (
            package
            for package in skills_root.iterdir()
            if package.is_dir() and (package / "manifest.json").is_file()
        ),
        key=lambda item: item.name,
    )
    entries = []
    for package in packages:
        entry = entry_from_package(package)
        if entry["name"] != package.name:
            raise RegistryError(f"manifest name differs from directory: {package.name}")
        entries.append(entry)
    return {
        "schema_version": current.get("schema_version"),
        "updated_at": current.get("updated_at"),
        "policy": current.get("policy"),
        "lifecycle_axes": current.get("lifecycle_axes"),
        "skills": entries,
    }


def self_test() -> dict[str, Any]:
    generated = render()
    skills = generated.get("skills")
    if not isinstance(skills, list) or not skills:
        raise RegistryError("rendered registry has no skills")
    names = [entry.get("name") for entry in skills if isinstance(entry, dict)]
    if names != sorted(names) or len(names) != len(set(names)):
        raise RegistryError("rendered registry names are not unique and sorted")
    if any(not isinstance(entry.get("package_digest"), str) for entry in skills):
        raise RegistryError("rendered registry lacks a package digest")
    return {"checks": 3, "package_count": len(skills), "status": "pass"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if sum(bool(value) for value in (args.check, args.output, args.self_test)) != 1:
        parser.error("choose exactly one of --check, --output, or --self-test")
    try:
        if args.self_test:
            result = self_test()
        else:
            generated = render()
            payload = json.dumps(generated, indent=2, ensure_ascii=False) + "\n"
            if args.check:
                current = strict_object(REGISTRY_PATH)
                if generated != current:
                    raise RegistryError("registry.json differs from generated package truth")
                result = {"package_count": len(generated["skills"]), "status": "pass"}
            else:
                output = args.output.resolve()
                if output.exists():
                    raise RegistryError("output already exists")
                if not output.parent.is_dir():
                    raise RegistryError("output parent does not exist")
                with output.open("x", encoding="utf-8") as handle:
                    handle.write(payload)
                result = {"output": str(output), "package_count": len(generated["skills"]), "status": "completed"}
    except (OSError, RegistryError) as exc:
        print(json.dumps({"error": str(exc), "status": "fail"}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
