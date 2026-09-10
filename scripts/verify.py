#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the existing Bio 02 gates through one small, deterministic entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUICK_COMMANDS = (
    ("registry-generated", (sys.executable, "scripts/render_registry.py", "--check")),
    ("skeleton", (sys.executable, "scripts/validate_skeleton.py")),
    ("validator-self-test", (sys.executable, "scripts/validate_skeleton.py", "--self-test")),
    ("installer-self-test", (sys.executable, "scripts/manage_skills.py", "--self-test")),
    ("workflow-self-test", (sys.executable, "tests/test_workflow.py")),
    ("diff-check", ("git", "diff", "--check")),
)
RELEASE_COMMANDS = (
    ("connector-self-test", (sys.executable, "scripts/run_research_connector.py", "--self-test")),
    ("wave-r1", (sys.executable, "scripts/run_wave_r1_minimal_reliability.py")),
    ("wave-r2", (sys.executable, "scripts/run_wave_r2_minimal_reliability.py")),
    ("wave-r3", (sys.executable, "scripts/run_wave_r3_minimal_reliability.py")),
    ("wave-r4", (sys.executable, "scripts/run_wave_r4_minimal_reliability.py")),
    ("wave-r5", (sys.executable, "scripts/run_wave_r5_minimal_reliability.py")),
)


class VerificationError(RuntimeError):
    """An existing gate failed or became non-deterministic."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_command(label: str, command: tuple[str, ...]) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"{label} could not complete: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"{label} failed with exit {completed.returncode}: {detail}")
    if completed.stderr:
        raise VerificationError(f"{label} produced unexpected stderr")
    return {
        "label": label,
        "stdout": completed.stdout,
        "stdout_sha256": sha256_text(completed.stdout),
        "stderr": completed.stderr,
        "stderr_sha256": sha256_text(completed.stderr),
    }


def execute(mode: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for label, command in QUICK_COMMANDS:
        results.append(run_command(label, command))

    deterministic: dict[str, str] = {}
    if mode == "release":
        for label, command in RELEASE_COMMANDS:
            first = run_command(label, command)
            second = run_command(label, command)
            if first["stdout"] != second["stdout"] or first["stderr"] != second["stderr"]:
                raise VerificationError(f"{label} output differed across two fresh runs")
            deterministic[label] = str(first["stdout_sha256"])
            results.append(first)

    return {
        "checks": len(results),
        "deterministic_replays": deterministic,
        "mode": mode,
        "results": [
            {
                "label": item["label"],
                "stderr_sha256": item["stderr_sha256"],
                "stdout_sha256": item["stdout_sha256"],
            }
            for item in results
        ],
        "status": "pass",
    }


def self_test() -> dict[str, Any]:
    labels = [label for label, _ in QUICK_COMMANDS + RELEASE_COMMANDS]
    if len(labels) != len(set(labels)):
        raise VerificationError("verification command labels are not unique")
    if set(label for label, _ in RELEASE_COMMANDS) != {
        "connector-self-test", "wave-r1", "wave-r2", "wave-r3", "wave-r4", "wave-r5",
    }:
        raise VerificationError("release command set differs from the retained gates")
    if sha256_text("") != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855":
        raise VerificationError("SHA-256 helper differs")
    return {"checks": 3, "status": "pass"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("quick", "release"), default="quick")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else execute(args.mode)
    except VerificationError as exc:
        print(json.dumps({"error": str(exc), "status": "fail"}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
