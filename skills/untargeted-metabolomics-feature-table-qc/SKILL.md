---
name: untargeted-metabolomics-feature-table-qc
description: "Check untargeted metabolomics feature tables, m/z, retention times and sample metadata under explicit intensity, zero and missing-value rules. Exclude normalization, annotation and differential testing."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Untargeted Metabolomics Feature-table QC

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use for bounded, offline structural and descriptive QC of a local untargeted-metabolomics TSV with exact feature rows, sample columns, m/z, retention time, and matching sample metadata. Require declared intensity, zero, and missing-value semantics; report joins, detected and missing counts, pooled-QC RSD, blank-to-study mean ratios, and batch/injection-order completeness. Exclude raw-MS peak picking, alignment, drift correction, filtering, normalization, imputation, compound annotation, differential or pathway analysis, contamination decisions, and biological or clinical interpretation.

## Owns

Audit one already-produced nonnegative feature-intensity table and its exact
sample metadata. Preserve the caller's declared zero/missing semantics and make
no pass/fail, contamination, or biological-quality decision.

## Inputs and intake

Require UTF-8 TSV files and a new JSON output path:

- feature table: first three headers exactly `feature_id`, `mz`, and
  `retention_time_seconds`; rows are features and remaining headers are sample
  IDs;
- metadata: exact headers `sample_id`, `sample_type`, `batch`, and
  `injection_order`; sample type is `study`, `pooled_qc`, or `blank`;
- declarations: one intensity semantic, one exact nonnumeric missing token, and
  whether numeric zero is `observed` or `missing`.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **table-semantics.** What do intensities, zeros, and the missing token mean?
   Recommended: use producer-recorded semantics and never infer them from the
   numeric distribution.
2. **sample-types.** Which metadata values identify study, pooled-QC, and blank
   injections? Recommended: export the fixed canonical labels above from the
   acquisition manifest; do not relabel samples from intensity patterns.

An explicit local QC request authorizes the bounded reads and one create-new
report.

## Run

```text
python3 scripts/qc_metabolomics_feature_table.py \
  --feature-table FEATURE_INTENSITIES.tsv --metadata SAMPLE_METADATA.tsv \
  --intensity-semantics raw-peak-area --missing-token NA \
  --zero-semantics missing --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only. It refuses leaf symlinks, ambiguous orientation, invalid or duplicate
IDs, nonfinite or negative values, invalid m/z or retention time, non-exact
sample joins, parent traversal, symlinked output parents, and existing outputs.

## Output contract

The deterministic create-new JSON report binds input fingerprints and exact
declarations to:

- exact sample joins and zero duplicate-ID counters;
- per-sample detected counts, explicit-token missing counts, and zero-as-missing
  counts;
- per-feature pooled-QC sample RSD, including explicit not-estimable reasons;
- per-feature blank-to-study arithmetic-mean ratios, including explicit
  not-estimable reasons;
- batch and injection-order completeness plus descriptive duplicate nonmissing
  injection positions.

Read [format and runtime boundaries](references/format-and-runtime-boundaries.md).

## Guardrails

- Never infer orientation, sample identity, sample type, intensity semantics,
  missing tokens, zero semantics, batch, or injection order.
- Never peak-pick raw MS, align features, drift-correct, filter, normalize,
  impute, annotate compounds, or run differential or pathway analysis.
- Never convert RSD, blank ratios, missingness, or metadata completeness into a
  pass/fail, contamination, carryover, exclusion, or biological conclusion.
- Never overwrite, mutate inputs, create directories, follow input/output
  symlinks, use the network, or start a subprocess.
- Require researcher review of producer semantics and descriptive output; this
  preview has no clinical or diagnostic authority.
