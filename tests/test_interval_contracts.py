#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Scientific interval algebra and boundary regressions on original tiny inputs."""
import copy, importlib.util, io, json, random, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(skill, script):
    spec = importlib.util.spec_from_file_location(
        script, ROOT / "skills" / skill / "scripts" / (script + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = module("genomic-interval-operations", "operate_intervals")
v = module("bioinformatics-result-visualization", "plot_results")
r = module("bioinformatics-qc-and-publication-reporting", "build_analysis_report")


class Contracts(unittest.TestCase):
    def setUp(self):
        e = ROOT / "examples/bed3-interval"
        self.a = (e / "a.bed").read_bytes()
        self.b = (e / "b.bed").read_bytes()
        self.contigs = (e / "toy.chrom.sizes").read_bytes()
        self.cfg = dict(
            operation="intersect",
            build_a="toy-v1",
            build_b="toy-v1",
            contig_build="toy-v1",
            coordinate_system="bed0-half-open",
            strand_policy="ignore",
            duplicates="preserve",
            adjacency=None,
        )

    def analyze(self):
        return m.analyze(self.a, self.b, self.contigs, self.cfg)

    def merge(self, policy):
        self.cfg.update(operation="merge", build_b=None, adjacency=policy)
        self.b = None
        return self.analyze()

    def test_hand_intersection_and_duplicate_coverage(self):
        d, f = self.analyze()
        self.assertEqual(d["reference"]["contig_order"], ["chr2", "chr1"])
        self.assertEqual(d["summary"]["output_rows"], 4)
        self.assertEqual(d["summary"]["output_row_bp_sum"], 17)
        self.assertEqual(d["summary"]["output_coverage_bp"], 12)
        self.assertEqual(
            f["result.bed"], b"chr2\t10\t12\nchr1\t5\t10\nchr1\t5\t10\nchr1\t10\t15\n"
        )
        self.assertEqual([t["a_row"] for t in d["trace"]], [4, 1, 3, 2])

    def test_bookended_and_overlap_only_differ(self):
        self.assertEqual(self.merge("overlap-only")[0]["summary"]["output_rows"], 3)
        self.assertEqual(self.merge("bookended")[0]["summary"]["output_rows"], 2)

    def test_no_positive_gap_bridging(self):
        self.a = b"chr1\t0\t5\nchr1\t6\t10\n"
        self.assertEqual(self.merge("bookended")[0]["summary"]["output_rows"], 2)

    def test_touching_is_not_intersection(self):
        self.a = b"chr1\t0\t10\n"
        self.b = b"chr1\t10\t20\n"
        d, f = self.analyze()
        self.assertEqual(d["results"], [])
        self.assertEqual(f["result.bed"], b"")

    def test_empty_inputs_and_trace_header(self):
        self.a = b""
        d, f = self.analyze()
        self.assertEqual(d["summary"]["output_coverage_bp"], 0)
        self.assertEqual(len(f["trace.tsv"].splitlines()), 1)
        self.assertEqual(self.merge("bookended")[1]["result.bed"], b"")

    def test_duplicate_rejection(self):
        self.cfg["duplicates"] = "reject"
        with self.assertRaises(m.UserError):
            self.analyze()

    def test_invalid_coordinates_headers_and_bed6(self):
        for raw in [
            b"chr1\t-1\t10\n",
            b"chr1\t1\t1\n",
            b"chr1\t0\t101\n",
            b"chr1\t0.5\t10\n",
            b"chr1\t01\t10\n",
            b"#header\n",
            b"chr1\t0\t10\vchr1\t15\t20",
            b"chr1\t0\t10\tname\t0\t+\n",
            b"chr1 0 10\n",
            b"\n",
        ]:
            self.a = raw
            with self.assertRaises(m.UserError):
                self.analyze()

    def test_unknown_contig_and_bad_dictionary(self):
        self.a = b"1\t0\t10\n"
        with self.assertRaises(m.UserError):
            self.analyze()
        for raw in [b"", b"chr1\t10\nchr1\t20\n", b"chr1\t0\n"]:
            with self.assertRaises(m.UserError):
                m.contigs_input(raw)

    def test_build_coordinate_strand_decisions(self):
        for key, value in [
            ("build_a", "unknown"),
            ("build_b", "other-build"),
            ("contig_build", None),
            ("coordinate_system", "one-based-closed"),
            ("strand_policy", "same"),
        ]:
            old = self.cfg[key]
            self.cfg[key] = value
            with self.assertRaises(m.UserError) as err:
                self.analyze()
            self.assertEqual(err.exception.status, "needs-decision")
            self.cfg[key] = old

    def test_operation_specific_arguments(self):
        self.cfg["adjacency"] = "bookended"
        with self.assertRaises(m.UserError):
            self.analyze()
        self.cfg.update(operation="merge", build_b=None)
        with self.assertRaises(m.UserError):
            self.analyze()

    def test_resource_caps_publish_nothing(self):
        self.a = b"chr1\t0\t10\n" * (m.MAX_ROWS + 1)
        with self.assertRaises(m.UserError) as err:
            self.analyze()
        self.assertEqual(err.exception.status, "needs-tool")
        self.a = b"chr1\t0\t10\n" * 150
        self.b = self.a
        with self.assertRaises(m.UserError) as err:
            self.analyze()
        self.assertEqual(err.exception.code, "pair-limit")

    def test_union_invariant_under_input_permutation(self):
        d, _ = self.analyze()
        self.a = b"\n".join(reversed(self.a.splitlines())) + b"\n"
        other, _ = self.analyze()
        self.assertEqual(d["results"], other["results"])
        self.assertEqual(d["summary"], other["summary"])

    def test_random_small_integer_base_set_oracle(self):
        rng = random.Random(741)

        def bases(raw):
            return {
                (chrom, p)
                for chrom, start, end in (
                    line.split() for line in raw.decode().splitlines()
                )
                for p in range(int(start), int(end))
            }

        for _ in range(50):

            def fixture():
                return m.table_bytes(
                    [
                        ["chr1", start, start + rng.randint(1, 10)]
                        for start in [
                            rng.randint(0, 30) for _ in range(rng.randint(0, 8))
                        ]
                    ]
                )

            self.a, self.b = fixture(), fixture()
            d, f = self.analyze()
            self.assertEqual(bases(f["result.bed"]), bases(self.a) & bases(self.b))
            self.assertEqual(
                d["summary"]["output_coverage_bp"], len(bases(self.a) & bases(self.b))
            )
            cfg = dict(self.cfg, operation="merge", build_b=None, adjacency="bookended")
            merged, files = m.analyze(self.a, None, self.contigs, cfg)
            self.assertEqual(bases(files["result.bed"]), bases(self.a))

    def test_merge_trace_accounts_for_every_row(self):
        d, _ = self.merge("bookended")
        self.assertEqual(sorted(t["a_row"] for t in d["trace"]), [1, 2, 3, 4])
        self.assertEqual(d["summary"]["output_coverage_bp"], 30)

    def test_plot_requires_contig_and_retains_duplicate_rows(self):
        d, _ = self.analyze()
        with self.assertRaises(v.UserError):
            v.interval_data(d, None)
        contig, rows = v.interval_data(d, "chr1")
        self.assertEqual(contig, "chr1")
        self.assertEqual(len([x for x in rows if x[0] == "result"]), 3)
        d["results"][0]["end"] = 999
        with self.assertRaises(v.UserError):
            v.interval_data(d, "chr1")

    def test_report_separates_union_and_pair_sum(self):
        d, _ = self.analyze()
        name, metrics, limits = r.summarize(d)
        self.assertEqual(name, "goose_bed3_intervals")
        self.assertEqual(metrics["output_row_bp_sum"], 17)
        self.assertEqual(metrics["output_coverage_bp"], 12)

    def test_create_new_and_symlink_boundary(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp).resolve()
            target = root / "out"
            m.new_bundle(str(target), {"result.bed": b""})
            with self.assertRaises(m.UserError):
                m.new_bundle(str(target), {"result.bed": b"changed"})
            self.assertEqual((target / "result.bed").read_bytes(), b"")
            link = root / "linked"
            link.symlink_to(target / "result.bed")
            with self.assertRaises(m.UserError):
                m.read_local(str(link))


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
