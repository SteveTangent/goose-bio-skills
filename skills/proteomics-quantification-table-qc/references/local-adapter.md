# Small protein table QC

Python >=3.10, standard library only. UTF-8 TSV inputs, at most 8 MiB each.
Matrix starts protein_id then 4–32 sample IDs and 1–10,000 protein rows. IDs are
unique simple text (letters/digits, underscore, period, colon, dash); leading
zeros are retained. Model eligibility requires 20 or more proteins. Sample
metadata has sample_id, condition, subject_id; add batch only for recorded
batch status. Exactly two groups are supported; letters lead group/batch labels
because the existing limma worker uses them as categorical design levels.

```text
python3 scripts/check_protein_table.py --self-test
python3 scripts/check_protein_table.py --matrix proteins.tsv --samples samples.tsv --feature-level protein --scale log2-normalized --normalization-method median-normalization --unit log2-intensity --zero-semantics value --batch-status absent --independent --numerator treated --denominator control --output qc-new
```

These declarations are supplied facts, not recommended processing choices.
Default missing tokens are blank and NA and are retained in config. Repeated
--missing-token options replace this list. Numeric measurements cannot be declared
missing tokens; choose --zero-semantics missing when producer zero means missing.
Unknown semantics, incomplete data, repeated subjects, unreplicated groups,
unknown normalization, constant batch or confounded design block model output.
No values or rows are imputed, normalized, transformed, filtered or deleted.

Outputs: qc.json, sample-qc.tsv (observed min/median/max and missing fraction),
protein-qc.tsv (missing count). Only ready inputs also produce model-matrix.tsv
(exact original bytes) and model-samples.tsv (sample_id/condition/[batch] in
matrix order). The original sample table, including subject identity, is bound
by its digest in QC. Deliberately narrowing the model table does not establish
independence; preserve and check the QC result before every downstream handoff.

Run protein-level-differential-abundance's run_limma.py on those exact outputs,
with --declared-protein-level-normalized-log2, matching numerator/denominator and
--covariate-column batch only when recorded. Its pinned environment remains
R 4.4.1 / limma 3.60.6. A valid design can still fail its statistical fit and does
not establish power or correct normalization. Missing-value methods need a
separate justified analysis; this narrow path does not claim limma universally
cannot process missing values.

Use the visualization Skill for protein volcano, PCA and sample-correlation;
--de-report must be the completed protein result, and matrix plots require
its exact model matrix with --matrix-scale log2-normalized. The report Skill
preserves QC units, readiness and protein effect direction. Explain protein
groups versus individual proteins and technical versus biological replication
only when those facts change the user's next step; ask the first blocking
question, not a long mandatory questionnaire.
