#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Meaningful dependency-free regressions; numerical smoke checks are separate."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
import tempfile
import hashlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(skill, script):
    spec = importlib.util.spec_from_file_location(
        script, ROOT / "skills" / skill / "scripts" / f"{script}.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


q = module("proteomics-quantification-table-qc", "check_protein_table")
p = module("distance-matrix-principal-coordinates-analysis", "run_pcoa")
v = module("bioinformatics-result-visualization", "plot_results")
r = module("bioinformatics-qc-and-publication-reporting", "build_analysis_report")


class Contracts(unittest.TestCase):
    def setUp(self):
        self.rows = [["protein_id", "001", "002", "003", "004"]] + [
            [f"{i:04d}", "10", "11", "12", "13"] for i in range(20)
        ]
        self.meta = [
            ["sample_id", "condition", "subject_id"],
            ["001", "control", "001"],
            ["002", "control", "002"],
            ["003", "treated", "003"],
            ["004", "treated", "004"],
        ]
        self.cfg = dict(
            feature_level="protein",
            scale="log2-normalized",
            normalization_method="synthetic",
            unit="log2-intensity",
            zero_semantics="value",
            batch_status="absent",
            independent=True,
            numerator="treated",
            denominator="control",
            missing_tokens=["", "NA"],
        )

    def qc(self):
        return q.inspect(q.table_bytes(self.rows), q.table_bytes(self.meta), self.cfg)

    def test_ready_preserves_matrix_bytes_and_text_ids(self):
        report, files = self.qc()
        self.assertTrue(report["model_ready"])
        self.assertEqual(files["model-matrix.tsv"], q.table_bytes(self.rows))
        self.assertIn(b"001\tcontrol", files["model-samples.tsv"])

    def test_missing_never_exports_model(self):
        for missing in ["", "NA"]:
            self.rows[1][1] = missing
            report, files = self.qc()
            self.assertEqual(report["summary"]["missing_cells"], 1)
            self.assertNotIn("model-matrix.tsv", files)
            self.assertEqual(report["status"], "needs-decision")

    def test_unknown_and_wrong_feature_facts_block(self):
        for key, value in [
            ("feature_level", "protein-group"),
            ("scale", "unknown"),
            ("independent", False),
            ("batch_status", "unknown"),
            ("zero_semantics", "unknown"),
            ("unit", "unknown"),
            ("normalization_method", "unknown"),
        ]:
            with self.subTest(key=key):
                old = self.cfg[key]
                self.cfg[key] = value
                self.assertFalse(self.qc()[0]["model_ready"])
                self.cfg[key] = old

    def test_repeated_subject_is_not_independent(self):
        self.meta[3][2] = "001"
        self.assertIn("independence", [x["code"] for x in self.qc()[0]["unresolved"]])

    def test_confounded_batch_blocks(self):
        self.cfg["batch_status"] = "recorded"
        self.meta[0].append("batch")
        for row in self.meta[1:]:
            row.append(row[1])
        self.assertIn(
            "design-confounded", [x["code"] for x in self.qc()[0]["unresolved"]]
        )

    def test_crossed_batch_is_estimable(self):
        self.cfg["batch_status"] = "recorded"
        self.meta[0].append("batch")
        for row, label in zip(self.meta[1:], ["A", "B", "A", "B"]):
            row.append(label)
        self.assertTrue(self.qc()[0]["model_ready"])

    def test_zero_semantics_changes_missingness_only_when_declared(self):
        self.rows[1][1] = "0"
        self.assertEqual(self.qc()[0]["summary"]["missing_cells"], 0)
        self.cfg["zero_semantics"] = "missing"
        self.assertEqual(self.qc()[0]["summary"]["missing_cells"], 1)

    def test_nonfinite_and_nonnumeric_rejected(self):
        for value in ["inf", "NaN", "censored"]:
            self.rows[1][1] = value
            with self.assertRaises(q.UserError):
                self.qc()

    def test_duplicate_samples_and_proteins_rejected(self):
        self.rows[2][0] = self.rows[1][0]
        with self.assertRaises(q.UserError):
            self.qc()

    def test_metadata_identity_mismatch_rejected(self):
        self.meta[1][0] = "wrong"
        with self.assertRaises(q.UserError):
            self.qc()

    def test_distance_asymmetry_diagonal_missing_negative_rejected(self):
        rows = [
            ["sample_id", "001", "002", "003"],
            ["001", "0", "1", "2"],
            ["002", "1", "0", "1"],
            ["003", "2", "1", "0"],
        ]
        for i, j, value in [(1, 2, "2"), (1, 1, "1"), (1, 2, "NA"), (1, 2, "-1")]:
            x = copy.deepcopy(rows)
            x[i][j] = value
            with self.assertRaises(p.UserError):
                p.distance_input(q.table_bytes(x), "square-tsv", "euclidean")

    def beta(self):
        return {
            "schema_version": "1.0",
            "analysis": {"method": "pairwise-descriptive-beta-diversity-distances"},
            "sample_ids": ["a", "b", "c"],
            "zero_depth_sample_ids": [],
            "pairs": [
                {
                    "sample_a": a,
                    "sample_b": b,
                    "zero_depth_sample_ids": [],
                    "bray_curtis": {
                        "status": "estimated",
                        "value": 0.5,
                        "numerator": 1,
                        "denominator": 2,
                    },
                }
                for a, b in [("a", "b"), ("a", "c"), ("b", "c")]
            ],
        }

    def test_native_beta_complete_and_ratios(self):
        x = self.beta()
        self.assertEqual(
            p.distance_input(q.encoded(x), "beta-json", "bray_curtis")[1][0][1], 0.5
        )
        x["pairs"][0]["bray_curtis"]["value"] = 0.9
        with self.assertRaises(p.UserError):
            p.distance_input(q.encoded(x), "beta-json", "bray_curtis")

    def test_native_beta_missing_duplicate_and_undefined_pairs(self):
        for mode in ["missing", "duplicate", "zero", "unavailable"]:
            x = self.beta()
            if mode == "missing":
                x["pairs"].pop()
            if mode == "duplicate":
                x["pairs"][1] = x["pairs"][0]
            if mode == "zero":
                x["zero_depth_sample_ids"] = ["a"]
            if mode == "unavailable":
                x["pairs"][0]["bray_curtis"]["status"] = "not-estimable"
            with self.assertRaises(p.UserError):
                p.distance_input(q.encoded(x), "beta-json", "bray_curtis")

    def test_protein_volcano_direction_and_unit(self):
        x = {
            "status": "completed",
            "tool": {
                "name": "protein-level-differential-abundance",
                "version": "0.13.0",
            },
            "results": [
                {
                    "protein_id": "001",
                    "effect_log2": -2,
                    "raw_p_value": 0.01,
                    "adjusted_p_value": 0.02,
                }
            ],
        }
        data, _ = v.volcano_data(v.protein_de(x), "padj", 0.05, 1)
        self.assertEqual(data[0][0], "001")
        self.assertEqual(data[0][4], "negative")

    def test_protein_handoff_worker_identity_without_bytecode_writes(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import manage_workflow as w

        model = module("protein-level-differential-abundance", "run_limma")
        tool = {"name": "protein-level-differential-abundance", "version": "0.13.0"}
        report = {
            "status": "completed",
            "tool": {
                **tool,
                "r_version": "4.4.1",
                "limma_version": "3.60.6",
                "worker_sha256": model.bundled_worker()[1],
            },
            "config": {},
            "input_sha256": {},
            "runtime_versions": {"R": "4.4.1", "limma": "3.60.6"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "model.json"
            path.write_text(json.dumps(report))
            step = {
                "skill": "protein-level-differential-abundance",
                "result": "model.json",
                "outputs": ["model.json"],
                "parameters": {},
                "tool_versions": {},
            }
            ctx = {"package": {"tool": tool}, "inputs": {}}
            before = w.identity(step["skill"])
            previous = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = False
                result = w.native_check(root, step, ctx)
            finally:
                sys.dont_write_bytecode = previous
            self.assertEqual(result["native_status"], "completed")
            self.assertEqual(w.identity(step["skill"]), before)
            report["tool"]["worker_sha256"] = "0" * 64
            path.write_text(json.dumps(report))
            with self.assertRaises(w.WorkflowError):
                w.native_check(root, step, ctx)

    def test_qc_report_preserves_needs_decision(self):
        self.cfg["scale"] = "unknown"
        report, _ = self.qc()
        name, metrics, limits = r.summarize(report)
        self.assertEqual(name, "goose_protein_table_qc")
        self.assertEqual(report["status"], "needs-decision")
        self.assertEqual(metrics["proteins"], 20)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(suite)
    if not result.wasSuccessful():
        print(stream.getvalue(), file=sys.stderr)
    print(
        json.dumps(
            {
                "status": "pass" if result.wasSuccessful() else "fail",
                "checks": result.testsRun,
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
