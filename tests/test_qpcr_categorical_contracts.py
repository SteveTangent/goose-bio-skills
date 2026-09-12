#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Small scientific contract regressions without numerical dependencies."""
import copy
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(skill, script):
    spec = importlib.util.spec_from_file_location(
        script, ROOT / "skills" / skill / "scripts" / (script + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


q = module("qpcr-relative-expression-and-qc", "analyze_qpcr")
c = module("independent-2x2-categorical-comparison", "compare_2x2")
v = module("bioinformatics-result-visualization", "plot_results")
r = module("bioinformatics-qc-and-publication-reporting", "build_analysis_report")


class Contracts(unittest.TestCase):
    def setUp(self):
        self.e = ROOT / "examples/qpcr-categorical"
        self.design = json.loads((self.e / "design.json").read_text())
        self.cq = list(
            __import__("csv").reader(
                io.StringIO((self.e / "cq.tsv").read_text()), delimiter="\t"
            )
        )
        self.samples = q.tsv((self.e / "samples.tsv").read_bytes())
        self.assays = q.tsv((self.e / "assays.tsv").read_bytes())

    def qpcr(self):
        return q.analyze(
            q.table_bytes(self.cq),
            q.table_bytes(self.samples),
            q.table_bytes(self.assays),
            self.design,
        )

    def blocked(self, code):
        result, files = self.qpcr()
        self.assertEqual(result["status"], "needs-decision")
        self.assertIn(code, [x["code"] for x in result["unresolved"]])
        self.assertNotIn("relative-expression.tsv", files)
        self.assertEqual(result["results"], [])

    def test_hand_computable_relative_expression(self):
        result, files = self.qpcr()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["subjects"], 8)
        self.assertEqual(result["summary"]["wells"], 96)
        for x in result["results"]:
            expected = (
                1 if x["group"] == "control" else (4 if x["target"] == "T1" else 0.5)
            )
            self.assertAlmostEqual(x["relative_expression"], expected)
        self.assertIn("group-summary.tsv", files)

    def test_unequal_efficiency_uses_log_quantity(self):
        self.assays[1][2] = "1.9"
        result, _ = self.qpcr()
        means = {
            (x["target"], x["group"]): x["geometric_mean_relative_expression"]
            for x in result["group_summary"]
        }
        self.assertAlmostEqual(means["T1", "treated"], 1.9**2)
        self.design["method"] = "delta-delta-cq"
        self.blocked("doubling-assumption")

    def test_reference_geometric_mean(self):
        for row in self.cq[1:]:
            if row[0] == "005" and row[1] == "R2":
                row[4] = str(float(row[4]) + 2)
        result, _ = self.qpcr()
        x = next(
            x
            for x in result["results"]
            if x["sample_id"] == "005" and x["target"] == "T1"
        )
        self.assertAlmostEqual(x["relative_expression"], 8)

    def test_row_order_does_not_change_values(self):
        first = self.qpcr()[0]["results"]
        self.cq[1:] = reversed(self.cq[1:])
        self.samples[1:] = reversed(self.samples[1:])
        self.assays[1:] = reversed(self.assays[1:])
        key = lambda x: (x["sample_id"], x["target"])
        self.assertEqual(
            sorted(first, key=key), sorted(self.qpcr()[0]["results"], key=key)
        )

    def test_undetermined_blocks_without_substitution(self):
        self.cq[1][4:] = ["", "undetermined"]
        self.blocked("unquantified-wells")
        self.cq[1][4] = "40"
        with self.assertRaises(q.UserError):
            self.qpcr()

    def test_missing_reference_cell(self):
        self.cq = [row for row in self.cq if not (row[0] == "001" and row[1] == "R1")]
        self.blocked("replicate-count")

    def test_technical_disagreement(self):
        self.cq[1][4] = "26"
        self.blocked("replicate-disagreement")

    def test_quantitative_range(self):
        self.assays[1][4] = "24"
        self.blocked("outside-quantitative-range")

    def test_unknown_assay_and_efficiency(self):
        self.design["assay"] = "unknown"
        self.blocked("assay-type")
        self.design["assay"] = "RT-qPCR"
        self.assays[1][2] = "unknown"
        self.blocked("assay-validation")

    def test_unknown_or_unreviewed_facts(self):
        for key, value, code in [
            ("method", "unknown", "method"),
            ("assay_qc_reviewed", False, "assay-qc"),
            ("reference_rationale", "unknown", "reference-rationale"),
            ("calibrator_group", "absent", "calibrator"),
            ("independent_subjects", False, "independence"),
        ]:
            old = self.design[key]
            self.design[key] = value
            self.blocked(code)
            self.design[key] = old

    def test_repeated_subject_and_multiple_runs(self):
        self.samples[2][1] = "001"
        self.blocked("independence")
        self.samples[2][1] = "002"
        self.cq[1][2] = "run2"
        self.blocked("multiple-runs")

    def test_invalid_well_values_and_duplicates(self):
        for value in ["NaN", "inf", "0", "-1"]:
            self.cq[1][4] = value
            with self.assertRaises(q.UserError):
                self.qpcr()
        self.cq[1][4] = "25"
        self.cq.append(self.cq[1])
        with self.assertRaises(q.UserError):
            self.qpcr()

    def test_plot_requires_explicit_target_and_consistent_records(self):
        report, _ = self.qpcr()
        with self.assertRaises(v.UserError):
            v.qpcr_data(report, None)
        v.qpcr_data(report, "T1")
        report["results"][0]["relative_expression"] = 999
        with self.assertRaises(v.UserError):
            v.qpcr_data(report, "T1")

    def test_counts_preserve_direction_and_reject_weights(self):
        raw = (self.e / "counts.tsv").read_bytes()
        self.assertEqual(c.counts_input(raw, "reference", "exposed"), [[11, 3], [1, 9]])
        for value in [b"1.5", b"-1", b"NaN", b"01"]:
            with self.assertRaises(c.UserError):
                c.counts_input(
                    raw.replace(b"exposed\t1\t", b"exposed\t" + value + b"\t"),
                    "exposed",
                    "reference",
                )

    def cfg(self):
        return dict(
            numerator="exposed",
            denominator="reference",
            event_label="response",
            nonevent_label="no-response",
            independent=False,
            sampling_design="cohort",
            confidence_level=0.95,
        )

    def test_nonindependent_and_unknown_design_no_statistics(self):
        cfg = self.cfg()
        raw = (self.e / "counts.tsv").read_bytes()
        result = c.analyze(raw, cfg)
        self.assertEqual(result["status"], "needs-decision")
        self.assertNotIn("effect", result)
        cfg.update(independent=True, sampling_design="unknown")
        self.assertEqual(c.analyze(raw, cfg)["status"], "needs-decision")

    def test_zero_margin_not_corrected(self):
        cfg = self.cfg()
        cfg["independent"] = True
        result = c.analyze(
            b"group\tevent\tnon_event\nexposed\t0\t0\nreference\t1\t5\n", cfg
        )
        self.assertEqual(result["status"], "needs-decision")
        self.assertNotIn("effect", result)

    def test_report_preserves_unresolved_qpcr(self):
        self.design["method"] = "unknown"
        report, _ = self.qpcr()
        name, metrics, limits = r.summarize(report)
        self.assertEqual(name, "goose_qpcr")
        self.assertEqual(metrics["subjects"], 8)

    def test_blank_validation_declarations_rejected(self):
        self.design["reference_rationale"] = " "
        with self.assertRaises(q.UserError):
            self.qpcr()
        self.design["reference_rationale"] = "synthetic"
        self.assays[1][-1] = " "
        with self.assertRaises(q.UserError):
            self.qpcr()

    def test_plot_rejects_duplicate_subjects(self):
        report, _ = self.qpcr()
        report["sample_metadata"][1]["subject_id"] = "001"
        for x in report["results"]:
            if x["sample_id"] == "002":
                x["subject_id"] = "001"
        with self.assertRaises(v.UserError):
            v.qpcr_data(report, "T1")

    def test_categorical_plot_preserves_method_and_infinity(self):
        report = {
            "status": "completed",
            "tool": {"name": "goose_independent_2x2", "version": "0.14.0"},
            "table": [[10, 0], [5, 5]],
            "config": dict(self.cfg(), independent=True),
            "row_labels": ["exposed", "reference"],
            "column_labels": ["response", "no-response"],
            "effect": {
                "measure": "odds-ratio",
                "estimate_method": "conditional maximum likelihood",
                "estimate": "infinity",
                "confidence_interval": {
                    "level": 0.95,
                    "method": "conditional exact equal-tailed",
                    "low": 1.19,
                    "high": "infinity",
                },
            },
            "test": {
                "method": "Fisher exact, two-sided probability ordering",
                "pvalue": 0.0325,
            },
        }
        self.assertEqual(v.categorical_data(report), [[10, 0], [5, 5]])
        for mode in ["method", "probability", "margin", "independence"]:
            x = copy.deepcopy(report)
            if mode == "method":
                x["effect"]["estimate_method"] = "Wald"
            if mode == "probability":
                x["test"]["pvalue"] = float("nan")
            if mode == "margin":
                x["table"] = [[0, 0], [5, 5]]
            if mode == "independence":
                x["config"]["independent"] = False
            with self.assertRaises(v.UserError):
                v.categorical_data(x)

    def test_native_qpcr_handoff_asks_plain_first_question(self):
        import hashlib
        import tempfile
        sys.path.insert(0, str(ROOT / 'scripts'))
        import manage_workflow as w
        self.cq[1][4:]=['','undetermined']
        report,files=self.qpcr()
        raw={'cq':q.table_bytes(self.cq),'samples':q.table_bytes(self.samples),'assays':q.table_bytes(self.assays),'design':q.encoded(self.design)}
        report['input_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}
        report['files']=list(files);report['output_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for k,v in raw.items():(root/(k+'.data')).write_bytes(v)
            for k,v in files.items():(root/k).write_bytes(v)
            (root/'qpcr.json').write_bytes(q.encoded(report))
            row=dict(id='qc',skill='qpcr-relative-expression-and-qc',inputs={k:k+'.data' for k in raw},parameters=self.design,fact_parameters={},required_facts=[],depends_on=[],result='qpcr.json',outputs=['qpcr.json',*files],receipt='receipt.json',tool_versions=report['runtime_versions'])
            (root/'plan.json').write_text(json.dumps(dict(schema_version='1.0',title='Unresolved Cq',facts={},steps=[row])))
            root,plan=w.load_plan(root/'plan.json');w.record(root,plan,'qc')
            state=w.evaluate(root,plan)['steps'][0]
            self.assertEqual(state['status'],'needs-decision')
            self.assertEqual(state['question'],report['unresolved'][0]['question'])
            self.assertNotIn("'code':",state['reason'])

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(q.UserError):
            q.parse_json(b'{"x":NaN}')


if __name__ == "__main__":
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)
    )
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
