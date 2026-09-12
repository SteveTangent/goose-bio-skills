#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""List task bundles, check local tool readiness, or install into a new directory."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from validate_skeleton import package_digest

ROOT = Path(__file__).resolve().parents[1]


def select(names, bundle):
    catalog = {
        p.parent.name: json.loads(p.read_text())
        for p in (ROOT / "skills").glob("*/manifest.json")
    }
    if bundle:
        bundles = json.loads((ROOT / "bundles.json").read_text())["bundles"]
        if bundle not in bundles:
            raise ValueError("Unknown bundle; use list to see available task bundles.")
        names = [*names, *bundles[bundle]["skills"]]
    if not names:
        raise ValueError("Choose --bundle or one or more --skill names.")
    ordered, visiting, done = [], set(), set()

    def visit(name):
        if name not in catalog:
            raise ValueError(f"Unknown skill: {name}")
        if name in visiting:
            raise ValueError("Skill dependency cycle detected.")
        if name in done:
            return
        visiting.add(name)
        for dependency in catalog[name]["depends_on"]:
            visit(dependency)
        visiting.remove(name)
        done.add(name)
        ordered.append(name)

    for name in names:
        visit(name)
    return ordered, catalog


def doctor(names, catalog):
    # Only the bounded helper paths listed here have a dependency inventory.
    # Manifest adapters may also describe broader guidance, so do not infer
    # execution readiness from a present Python interpreter alone.
    inventoried = {
        "bioinformatics-result-visualization",
        "ranked-gene-set-enrichment",
        "over-representation-analysis",  # Local GMT path uses the standard library.
        "count-based-differential-expression",  # DESeq2 path only.
        "normalized-microarray-differential-expression",
        "protein-level-differential-abundance",
        "distance-matrix-principal-coordinates-analysis",
        "two-group-comparison-and-effect-estimation",
        "correlation-and-association-screening",
        "single-cell-object-io-and-qc",
        "single-cell-core-analysis",
        "single-cell-pseudobulk-aggregation",
        "statistical-analysis-and-multiple-testing",
    }
    stdlib_adapters = {"Python standard library", "Python 3.10+ standard library"}
    unchecked = [
        name
        for name in names
        if catalog[name]["script_verification"]["bundled_scripts"]
        and name not in inventoried
        and not (
            catalog[name].get("local_adapters")
            and set(catalog[name]["local_adapters"]) <= stdlib_adapters
        )
    ]
    requirements = {}
    if "bioinformatics-result-visualization" in names:
        requirements.update(numpy=None, matplotlib=None)
    if "distance-matrix-principal-coordinates-analysis" in names:
        requirements.update(numpy=None)
    if "ranked-gene-set-enrichment" in names:
        requirements.update(gseapy="1.3.0", pandas=None)
    if set(names) & {
        "two-group-comparison-and-effect-estimation",
        "correlation-and-association-screening",
    }:
        requirements.update(numpy=None, scipy=None)
    if set(names) & {
        "single-cell-object-io-and-qc",
        "single-cell-core-analysis",
        "single-cell-pseudobulk-aggregation",
    }:
        requirements.update(
            numpy=None, scipy=None, anndata="0.13.3.post0", h5py="3.16.0"
        )
    if "single-cell-core-analysis" in names:
        requirements.update(scanpy="1.12.4", igraph="0.11.9")
    checks = [
        {
            "tool": "Python",
            "version": sys.version.split()[0],
            "ready": sys.version_info >= (3, 10),
        }
    ]
    for name, required in sorted(requirements.items()):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        checks.append(
            {
                "tool": name,
                "version": version,
                "required_version": required,
                "ready": version is not None
                and (required is None or version == required),
            }
        )
    if "count-based-differential-expression" in names:
        runner = shutil.which("Rscript")
        if runner:
            # Fixed local metadata query; no user expression, installation or network.
            expression = 'for (p in c("DESeq2","jsonlite")) { cat(p,"=",if (requireNamespace(p,quietly=TRUE)) as.character(packageVersion(p)) else "missing","\\n",sep="") }'
            try:
                result = subprocess.run(
                    [runner, "--vanilla", "-e", expression],
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                versions = dict(
                    line.split("=", 1)
                    for line in result.stdout.splitlines()
                    if "=" in line
                )
                checks.append(
                    {
                        "tool": "R / DESeq2 / jsonlite",
                        "versions": versions,
                        "ready": result.returncode == 0
                        and all(
                            versions.get(p) not in {None, "missing"}
                            for p in ["DESeq2", "jsonlite"]
                        ),
                    }
                )
            except (OSError, subprocess.TimeoutExpired):
                checks.append(
                    {
                        "tool": "R package metadata",
                        "ready": False,
                        "reason": "Local version query failed or timed out.",
                    }
                )
        else:
            checks.append({"tool": "Rscript", "ready": False})
    if set(names) & {"normalized-microarray-differential-expression", "protein-level-differential-abundance"}:
        runner = shutil.which("Rscript")
        versions = {}
        if runner:
            expression = 'cat("R=",as.character(getRversion()),"\\n",sep="");cat("limma=",if(requireNamespace("limma",quietly=TRUE)) as.character(packageVersion("limma")) else "missing","\\n",sep="")'
            try:
                result = subprocess.run([runner,"--vanilla","-e",expression],text=True,capture_output=True,timeout=30,check=False)
                if result.returncode == 0:
                    versions = dict(line.split("=",1) for line in result.stdout.splitlines() if "=" in line)
            except (OSError, subprocess.TimeoutExpired):
                pass
        checks.append({"tool":"normalized expression/protein R / limma","versions":versions,"required_versions":{"R":"4.4.1","limma":"3.60.6"},"ready":versions=={"R":"4.4.1","limma":"3.60.6"}})
    guidance = [
        n for n in names if not catalog[n]["script_verification"]["bundled_scripts"]
    ]
    return {
        "status": "completed",
        "selected": names,
        "checked_helpers_ready": not unchecked and all(x["ready"] for x in checks),
        "dependency_inventory_complete": not unchecked,
        "unchecked_helpers": unchecked,
        "checks": checks,
        "guidance_only": guidance,
        "limitations": [
            "Readiness is a dependency inventory, not an analysis or host-routing check.",
            "Unchecked helpers require their own adapter checks; missing coverage is not a passed check.",
            "Other declared adapters, including those beyond the inventoried helper path, require their own environment checks.",
            "DESeq2 execution still requires its exact installed version and a compatible declared design.",
        ],
        "automatic_installation": False,
    }


def no_symlink(path):
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError("Symlink paths are not accepted.")


def install(names, destination):
    destination = Path(os.path.abspath(destination))
    no_symlink(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError(
            "Use a NEW destination whose parent already exists; existing installations are never merged."
        )
    registry = {
        x["name"]: x["package_digest"]
        for x in json.loads((ROOT / "registry.json").read_text())["skills"]
    }
    with tempfile.TemporaryDirectory(
        prefix=".goose-install-", dir=destination.parent
    ) as tmp:
        staging = Path(tmp)
        for name in names:
            source = ROOT / "skills" / name
            no_symlink(source)
            if (
                any(p.is_symlink() for p in source.rglob("*"))
                or package_digest(source) != registry[name]
            ):
                raise ValueError(f"Package identity or digest check failed: {name}")
            shutil.copytree(source, staging / name)
            if package_digest(staging / name) != registry[name]:
                raise ValueError(f"Staged package digest differs: {name}")
        destination.mkdir(
            mode=0o700
        )  # Exclusive create: never replaces even an empty directory.
        identity = destination.stat().st_ino
        try:
            for name in names:
                shutil.copytree(staging / name, destination / name)
                if package_digest(destination / name) != registry[name]:
                    raise ValueError(f"Installed package digest differs: {name}")
        except Exception:
            if not destination.is_symlink() and destination.stat().st_ino == identity:
                shutil.rmtree(destination)
            raise
    return {
        "status": "completed",
        "installed": names,
        "package_digests": {n: registry[n] for n in names},
        "external_tools_installed": False,
    }


def self_test():
    names, catalog = select(["count-based-differential-expression"], None)
    assert names.index("statistical-analysis-and-multiple-testing") < names.index(
        "count-based-differential-expression"
    )
    for name in ["read-alignment-selection-and-execution"]:
        result = doctor([name], catalog)
        assert not result["checked_helpers_ready"]
        assert not result["dependency_inventory_complete"]
        assert result["unchecked_helpers"] == [name]
    result = doctor(["protein-level-differential-abundance"], catalog)
    assert result["dependency_inventory_complete"] and not result["unchecked_helpers"]
    result = doctor(["statistical-analysis-and-multiple-testing"], catalog)
    assert result["checked_helpers_ready"] and result["dependency_inventory_complete"]
    unknown = {
        "new-helper": {
            "script_verification": {"bundled_scripts": True},
            "local_adapters": ["Unknown runtime"],
        }
    }
    assert doctor(["new-helper"], unknown)["unchecked_helpers"] == ["new-helper"]
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp).resolve() / "skills"
        first = install(["statistical-analysis-and-multiple-testing"], target)
        assert first["status"] == "completed"
        digest = package_digest(target / "statistical-analysis-and-multiple-testing")
        try:
            install(names, target)
        except ValueError:
            pass
        else:
            raise AssertionError("Existing destination accepted.")
        assert (
            package_digest(target / "statistical-analysis-and-multiple-testing")
            == digest
        )
        link = Path(tmp).resolve() / "link"
        link.symlink_to(target, target_is_directory=True)
        try:
            install(names, link / "nested")
        except ValueError:
            pass
        else:
            raise AssertionError("Symlink ancestor accepted.")
    return {"status": "pass", "checks": 8}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", nargs="?", choices=["list", "doctor", "install"], default="list"
    )
    parser.add_argument("--bundle")
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--destination")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            result = self_test()
        elif args.action == "list":
            result = json.loads((ROOT / "bundles.json").read_text())
        else:
            names, catalog = select(args.skill, args.bundle)
            if args.action == "doctor":
                result = doctor(names, catalog)
            else:
                if not args.destination:
                    raise ValueError(
                        "Installation requires an explicit new --destination."
                    )
                result = install(names, args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(
            json.dumps({"status": "invalid-input", "error": str(exc)}), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
