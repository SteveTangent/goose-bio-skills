#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression checks for expression inputs, reference preparation and handoffs."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import manage_workflow as w


def module(skill, file):
    spec = importlib.util.spec_from_file_location(file, ROOT / 'skills' / skill / 'scripts' / (file + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


micro = module('normalized-microarray-differential-expression', 'run_microarray_de')
mapper = module('biological-database-record-retrieval-and-identifier-resolution', 'resolve_local_ids')


class ExpressionContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.rows = [['gene_id', 'a', 'b', 'c', 'd']] + [[f'p{i}', '5.1', '5.4', '6.3', '6.1'] for i in range(20)]
        self.meta = [['sample_id', 'condition', 'subject_id'], ['a', 'control', 'a'], ['b', 'control', 'b'], ['c', 'treated', 'c'], ['d', 'treated', 'd']]
        self.cfg = dict(assay='microarray', scale='log2-normalized', feature_unit='probe', taxon='9606', namespace='synthetic', platform='synthetic', normalization_provenance='simulated log2', numerator='treated', denominator='control', covariate='', alpha=.05, independent_samples_declared=True)

    def validate(self, rows=None, meta=None, cfg=None):
        return micro.validate_inputs(micro.table_bytes(self.rows if rows is None else rows), micro.table_bytes(self.meta if meta is None else meta), self.cfg if cfg is None else cfg)

    def run_helper(self, skill, script, args):
        r = subprocess.run([sys.executable, str(ROOT / 'skills' / skill / 'scripts' / script), *args], cwd=self.root, text=True, capture_output=True, timeout=30, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_geo_feature_heading_preserves_probe_identity(self):
        rows=copy.deepcopy(self.rows)
        rows[0][0]="feature_id"
        self.assertEqual(self.validate(rows=rows)[2],[r[0] for r in rows[1:]])

    def test_transcript_counts_and_tpm_do_not_select_microarray(self):
        for key, value in [('assay', 'RNA-seq'), ('scale', 'TPM'), ('scale', 'raw-counts')]:
            with self.subTest(key=key, value=value), self.assertRaises(micro.UserError):
                self.validate(cfg={**self.cfg, key: value})

    def test_missing_and_infinite_expression_requires_decision(self):
        for value in ['NA', 'NaN', 'inf']:
            rows = copy.deepcopy(self.rows)
            rows[1][1] = value
            with self.subTest(value=value), self.assertRaises(micro.UserError):
                self.validate(rows=rows)

    def test_pairing_and_complete_batch_confounding_are_rejected(self):
        meta = copy.deepcopy(self.meta)
        meta[3][2] = 'a'
        with self.assertRaises(micro.UserError):
            self.validate(meta=meta)
        meta = [self.meta[0]+['batch']]+[r+[r[1]] for r in self.meta[1:]]
        with self.assertRaises(micro.UserError):
            self.validate(meta=meta, cfg={**self.cfg, 'covariate':'batch'})

    def test_reference_conversion_retains_ambiguous_pairs(self):
        (self.root/'reference.tsv').write_text('probe\tgene\ttaxon\np1\tg1\t9606\np1\tg2\t9606\np1\tg1\t9606\np2\tg1\t9606\n')
        self.run_helper('biological-database-record-retrieval-and-identifier-resolution','resolve_local_ids.py',['--prepare-reference','mapping','--reference-input','reference.tsv','--source-column','probe','--target-column','gene','--taxon-column','taxon','--source-namespace','probe','--target-namespace','gene','--taxon','9606','--mapping-release','test','--output','out'])
        result=json.loads((self.root/'out/resource.json').read_text())
        self.assertEqual(result['rows'],3)
        self.assertEqual(result['exact_duplicates_removed'],1)
        self.assertIn('p1\tg2', (self.root/'out/mapping.tsv').read_text())
        self.assertEqual(result['output_sha256']['mapping.tsv'],w.digest((self.root/'out/mapping.tsv').read_bytes()))

    def test_gmt_keeps_members_and_does_not_fetch_descriptions(self):
        (self.root/'sets.gmt').write_text('S\thttps://example.invalid/do-not-fetch\tg1\tg2\tg1\n')
        self.run_helper('biological-database-record-retrieval-and-identifier-resolution','resolve_local_ids.py',['--prepare-reference','gene-sets','--reference-input','sets.gmt','--taxon','9606','--target-namespace','gene','--mapping-release','test','--output','out'])
        result=json.loads((self.root/'out/resource.json').read_text())
        self.assertEqual(result['rows'],2)
        self.assertEqual(result['exact_duplicates_removed'],1)
        self.assertFalse(result['network_performed'])
        self.assertNotIn('https:',(self.root/'out/gene-sets.tsv').read_text())

    def test_design_counts_units_and_retains_full_metadata(self):
        (self.root/'samples.tsv').write_bytes(micro.table_bytes(self.meta))
        self.run_helper('bioinformatics-format-and-identifier-validation','validate_sample_table.py',['--metadata','samples.tsv','--design','independent','--group-column','condition','--subject-column','subject_id','--numerator','treated','--denominator','control','--output','out'])
        result=json.loads((self.root/'out/validation.json').read_text())
        self.assertEqual(result['design']['groups']['control']['declared_units'],2)
        self.assertIn('subject_id',(self.root/'out/samples.tsv').read_text())
        self.assertEqual((self.root/'out/count-de-samples.tsv').read_text().splitlines()[0],'sample_id\tcondition')

    def test_paired_expression_route_retains_decision(self):
        meta=copy.deepcopy(self.meta)
        meta[3][2]='a';meta[4][2]='b'
        (self.root/'samples.tsv').write_bytes(micro.table_bytes(meta))
        self.run_helper('bioinformatics-format-and-identifier-validation','validate_sample_table.py',['--metadata','samples.tsv','--design','paired','--group-column','condition','--subject-column','subject_id','--numerator','treated','--denominator','control','--output','out'])
        result=json.loads((self.root/'out/validation.json').read_text())
        self.assertEqual(result['status'],'needs-decision')
        self.assertEqual(result['design']['paired_units'],2)
        self.assertFalse((self.root/'out/count-de-samples.tsv').exists())

    def test_native_result_can_exceed_plan_limit(self):
        (self.root/'large.json').write_text(json.dumps({'padding':'a'*(1024*1024)}))
        with self.assertRaises(w.WorkflowError):
            w.read_json(self.root/'large.json')
        self.assertIn('padding', w.read_json(self.root/'large.json',limit=w.MAX_FILE))

    def test_legacy_count_worker_identity_is_checked(self):
        count=module('count-based-differential-expression','run_count_de')
        inputs={'counts':'a'*64,'metadata':'b'*64}
        step={'skill':'count-based-differential-expression','result':'de.json','parameters':{},'tool_versions':{},'outputs':['de.json']}
        ctx={'package':w.identity(step['skill']),'inputs':inputs}
        result={'status':'completed','method':'DESeq2','adapter_version':count.VERSION,'input_sha256':inputs,'worker_sha256':w.digest(count.WORKER.encode()),'model':{'versions':{'R':'fixture','DESeq2':'fixture'}}}
        (self.root/'de.json').write_text(json.dumps(result))
        self.assertEqual(w.native_check(self.root,step,ctx)['handoff_status'],'completed')
        result['worker_sha256']='c'*64
        (self.root/'de.json').write_text(json.dumps(result))
        with self.assertRaises(w.WorkflowError):
            w.native_check(self.root,step,ctx)

    def test_resource_output_hash_is_checked(self):
        step={'skill':'biological-database-record-retrieval-and-identifier-resolution','result':'resource.json','parameters':{},'tool_versions':{},'outputs':['resource.json']}
        ctx={'package':w.identity(step['skill']),'inputs':{'reference':'a'*64}}
        (self.root/'mapping.tsv').write_text('original')
        result={'status':'completed','tool':ctx['package']['tool'],'input_sha256':ctx['inputs'],'files':['mapping.tsv'],'output_sha256':{'mapping.tsv':w.digest(b'original')}}
        (self.root/'resource.json').write_text(json.dumps(result))
        self.assertEqual(w.native_check(self.root,step,ctx)['handoff_status'],'completed')
        (self.root/'mapping.tsv').write_text('changed')
        with self.assertRaises(w.WorkflowError):
            w.native_check(self.root,step,ctx)


if __name__=='__main__':
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExpressionContracts))
    if not result.wasSuccessful():
        print(stream.getvalue(),file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({'status':'pass','checks':result.testsRun}))
