#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded handoff regressions, using synthetic native envelopes."""

import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import manage_workflow as w


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "data.tsv").write_text("sample\tvalue\na\t1\n")
        sha = w.digest(w.read_bytes(self.root / "data.tsv"))
        self.plan = {
            "schema_version": "1.0",
            "title": "Synthetic handoff",
            "facts": {
                "scale": {
                    "value": "continuous",
                    "source": "user",
                    "note": "Synthetic test declaration",
                    "evidence": {"data.tsv": sha},
                }
            },
            "steps": [
                {
                    "id": "compare",
                    "skill": "two-group-comparison-and-effect-estimation",
                    "inputs": {"table": "data.tsv"},
                    "parameters": {"scale": "continuous"},
                    "fact_parameters": {"scale": "scale"},
                    "required_facts": ["scale"],
                    "depends_on": [],
                    "result": "result.json",
                    "outputs": ["result.json"],
                    "receipt": "receipt.json",
                    "tool_versions": {"numpy": "fixture"},
                }
            ],
        }
        self.result = {
            "tool": w.identity(self.plan["steps"][0]["skill"])["tool"],
            "status": "completed",
            "config": {"scale": "continuous"},
            "input_sha256": {"table": sha},
            "runtime_versions": {"numpy": "fixture"},
        }
        self.save()
        self.save_result()

    def save(self):
        (self.root / "analysis.json").write_text(json.dumps(self.plan))

    def save_result(self):
        (self.root / "result.json").write_text(json.dumps(self.result))

    def status(self):
        root, plan = w.load_plan(self.root / "analysis.json")
        return w.evaluate(root, plan)

    def record(self):
        root, plan = w.load_plan(self.root / "analysis.json")
        return w.record(root, plan, "compare")

    def child(self):
        step = copy.deepcopy(self.plan["steps"][0])
        step.update(
            id="figure",
            skill="bioinformatics-result-visualization",
            inputs={"result": "result.json"},
            parameters={"kind": "groups"},
            fact_parameters={},
            required_facts=[],
            depends_on=["compare"],
            result="figure.json",
            outputs=["figure.json"],
            receipt="figure-receipt.json",
            tool_versions={},
        )
        self.plan["steps"].append(step)
        self.save()
        (self.root / "figure.json").write_text(
            json.dumps(
                {
                    "tool": w.identity(step["skill"])["tool"],
                    "status": "completed",
                    "config": {"kind": "groups"},
                    "input_sha256": {
                        "result": w.digest(w.read_bytes(self.root / "result.json"))
                    },
                }
            )
        )

    def test_completed_and_reusable(self):
        self.assertEqual(self.status()["steps"][0]["status"], "ready")
        self.record()
        self.assertEqual(self.status()["status"], "completed")

    def test_unknown_fact_one_question(self):
        self.plan["facts"]["scale"]["source"] = "unknown"
        self.save()
        self.assertIn("question", self.status()["next_action"])
        with self.assertRaises(w.WorkflowError):
            self.record()
        self.assertFalse((self.root / "receipt.json").exists())

    def test_input_change_requires_fact_refresh(self):
        self.record()
        (self.root / "data.tsv").write_text("changed\n")
        self.assertEqual(self.status()["steps"][0]["status"], "needs-decision")

    def test_changed_unbound_input_is_stale(self):
        self.plan["steps"][0].update(required_facts=[], fact_parameters={})
        self.save()
        self.record()
        (self.root / "data.tsv").write_text("changed\n")
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_parameter_drift(self):
        self.record()
        self.plan["steps"][0]["parameters"]["confidence"] = 0.9
        self.save()
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_native_wrong_input(self):
        self.result["input_sha256"]["table"] = "0" * 64
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()
        self.assertFalse((self.root / "receipt.json").exists())

    def test_native_wrong_parameters(self):
        self.result["config"]["scale"] = "raw-counts"
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_wrong_tool_or_version(self):
        self.result["tool"]["version"] = "unreviewed"
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_wrong_runtime(self):
        self.result["runtime_versions"]["numpy"] = "different"
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_runtime_requirement_change(self):
        self.record()
        self.plan["steps"][0]["tool_versions"]["numpy"] = "new"
        self.save()
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_partial_blocks_downstream(self):
        self.result["status"] = "partial"
        self.save_result()
        self.child()
        self.record()
        state = self.status()
        self.assertEqual([r["status"] for r in state["steps"]], ["partial", "blocked"])
        self.assertEqual(state["status"], "incomplete")

    def test_needs_review_preserved(self):
        self.result["status"] = "needs-review"
        self.save_result()
        self.record()
        self.assertEqual(self.status()["steps"][0]["status"], "needs-review")

    def test_no_false_completed_status(self):
        self.result["status"] = "pass"
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_transitive_stale(self):
        self.child()
        self.record()
        w.record(self.root, self.plan, "figure")
        self.assertEqual(self.status()["status"], "completed")
        self.result["extra"] = "changed"
        self.save_result()
        self.assertEqual(
            [r["status"] for r in self.status()["steps"]], ["stale", "blocked"]
        )

    def test_missing_dependency_rejected(self):
        self.child()
        self.plan["steps"][1]["depends_on"] = []
        self.save()
        with self.assertRaises(w.WorkflowError):
            self.status()

    def test_fact_parameter_conflict(self):
        self.plan["steps"][0]["parameters"]["scale"] = "raw-counts"
        self.save()
        self.assertEqual(self.status()["steps"][0]["status"], "needs-decision")

    def test_receipt_never_overwritten(self):
        self.record()
        before = (self.root / "receipt.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.record()
        self.assertEqual(before, (self.root / "receipt.json").read_bytes())

    def test_rerun_with_new_receipt(self):
        self.record()
        self.plan["steps"][0]["receipt"] = "receipt-2.json"
        self.save()
        self.assertEqual(self.status()["steps"][0]["status"], "ready")
        self.record()
        self.assertEqual(self.status()["status"], "completed")
        self.assertTrue((self.root / "receipt.json").exists())

    def test_outputs_missing_or_changed(self):
        self.plan["steps"][0]["outputs"].append("figure.svg")
        (self.root / "figure.svg").write_text("synthetic")
        self.save()
        self.record()
        (self.root / "figure.svg").unlink()
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_duplicate_json_rejected(self):
        (self.root / "analysis.json").write_text(
            '{"schema_version":"1.0","schema_version":"2.0"}'
        )
        with self.assertRaises(w.WorkflowError):
            self.status()

    def test_parent_path_rejected(self):
        self.plan["steps"][0]["inputs"]["table"] = "../secret.tsv"
        self.save()
        with self.assertRaises(w.WorkflowError):
            self.status()

    def test_symlink_rejected(self):
        (self.root / "data.tsv").unlink()
        (self.root / "data.tsv").symlink_to(self.root / "result.json")
        self.assertEqual(self.status()["steps"][0]["status"], "needs-decision")
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_nonregular_input_rejected_without_blocking(self):
        (self.root / "data.tsv").unlink()
        os.mkfifo(self.root / "data.tsv")
        with self.assertRaises(w.WorkflowError):
            w.read_bytes(self.root / "data.tsv")

    def test_cycle_rejected(self):
        self.plan["steps"][0]["depends_on"] = ["compare"]
        self.save()
        with self.assertRaises(w.WorkflowError):
            self.status()

    def test_confirm_creates_new_plan(self):
        before = (self.root / "analysis.json").read_bytes()
        w.confirm(
            self.root,
            self.plan,
            "scale",
            "continuous",
            "user",
            "User confirmed",
            ["data.tsv"],
            "confirmed.json",
        )
        self.assertEqual(before, (self.root / "analysis.json").read_bytes())
        _, updated = w.load_plan(self.root / "confirmed.json")
        self.assertIsNone(w.fact_problem(self.root, updated["facts"]["scale"]))

    def test_overview_escapes_untrusted_title(self):
        self.plan["title"] = "<script>alert(1)</script> [link](https://example.invalid)"
        self.save()
        self.record()
        w.overview(self.root, self.status(), "overview.md")
        text = (self.root / "overview.md").read_text()
        self.assertNotIn("<script>", text)
        self.assertNotIn("[link]", text)
        self.assertIn("](result.json)", text)

    def test_receipt_context_tamper(self):
        self.record()
        p = self.root / "receipt.json"
        saved = json.loads(p.read_text())
        saved["context"]["inputs"] = {}
        p.write_text(json.dumps(saved))
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_reported_failure_blocks_and_can_resume(self):
        self.child()
        w.note_failure(self.root, self.plan, "compare", "Declared tool unavailable")
        self.assertEqual(
            [r["status"] for r in self.status()["steps"]],
            ["blocked-or-failed", "blocked"],
        )
        self.plan["steps"][0]["receipt"] = "retry.json"
        self.save()
        self.record()
        self.assertEqual(self.status()["steps"][0]["status"], "completed")

    def test_failure_needs_explanation(self):
        with self.assertRaises(w.WorkflowError):
            w.note_failure(self.root, self.plan, "compare", "")
        self.assertFalse((self.root / "receipt.json").exists())

    def test_malformed_receipt_is_stale(self):
        (self.root / "receipt.json").write_text("[]")
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_malformed_runtime_metadata(self):
        self.result["runtime_versions"] = ["not-a-mapping"]
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_native_extra_output_inventory(self):
        self.result["files"] = ["extra.tsv"]
        (self.root / "extra.tsv").write_text("extra")
        self.save_result()
        self.record()
        (self.root / "extra.tsv").unlink()
        self.assertEqual(self.status()["steps"][0]["status"], "stale")

    def test_native_output_path_escape(self):
        self.result["files"] = ["../foreign.tsv"]
        self.save_result()
        with self.assertRaises(w.WorkflowError):
            self.record()

    def test_report_complete_file_preserves_partial_sources(self):
        self.result["status"] = "needs-decision"
        self.save_result()
        self.record()
        source_hash = w.digest(w.read_bytes(self.root / "result.json"))
        step = copy.deepcopy(self.plan["steps"][0])
        step.update(
            id="report",
            skill="bioinformatics-qc-and-publication-reporting",
            inputs={"source:comparison": "result.json"},
            parameters={},
            fact_parameters={},
            required_facts=[],
            depends_on=["compare"],
            result="report.json",
            outputs=["report.json"],
            receipt="report-receipt.json",
            tool_versions={},
        )
        self.plan["steps"].append(step)
        self.save()
        (self.root / "source-copy.json").write_bytes(
            (self.root / "result.json").read_bytes()
        )
        report = {
            "tool": w.identity(step["skill"])["tool"],
            "status": "completed",
            "source_outcome": "partial",
            "sources": [
                {
                    "label": "comparison",
                    "sha256": source_hash,
                    "file": "source-copy.json",
                    "status": "needs-decision",
                }
            ],
            "figures": [],
            "files": ["source-copy.json"],
        }
        (self.root / "report.json").write_text(json.dumps(report))
        w.record(self.root, self.plan, "report")
        state = self.status()
        self.assertEqual(
            [r["status"] for r in state["steps"]], ["needs-decision", "partial"]
        )
        self.assertIn("source-copy.json", state["steps"][1]["outputs"])

    def test_package_drift(self):
        self.record()
        from unittest.mock import patch

        original = w.identity

        def changed(skill):
            value = original(skill)
            value["package_version"] = "changed"
            return value

        with patch.object(w, "identity", changed):
            self.assertEqual(self.status()["steps"][0]["status"], "stale")


if __name__ == "__main__":
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests)
    )
    if not result.wasSuccessful():
        print(stream.getvalue(), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"status": "pass", "checks": result.testsRun}))
