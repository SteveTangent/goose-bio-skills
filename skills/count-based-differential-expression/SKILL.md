---
name: count-based-differential-expression
description: "Analyze raw count matrices and sample metadata for one declared differential-expression contrast. Use the bounded local DESeq2 adapter when compatible; exclude FASTQ processing, enrichment and cross-adapter parity claims."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Count-based Differential Expression

`Preview + reviewed`; the helper self-test and one small public-data execution
smoke check passed. Agent evaluation, scientific benchmarking and expert review
were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user has declared raw counts plus sample metadata and needs a group or covariate differential-expression analysis. Exclude: FASTQ-to-count processing; pathway enrichment; assuming two software adapters are numerically identical.

## Owns

Estimate a declared contrast from counts with a defensible design, diagnostics and multiple-testing record. Apply the detailed scope below.

## Inputs

- feature-by-sample count matrix
- sample metadata
- design formula and target contrast
- filtering and independent-filter policy

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **primary-contrast.** What is the primary differential-expression contrast? Recommended: Declare one estimable contrast before fitting the model.

## Bounded local execution

Read [the adapter contract](references/deseq2-adapter.md) before using the
bundled helper. Require explicit count semantics, contrast, covariate, filtering
and diagnostic policies. It accepts one two-level contrast and at most one
categorical adjustment; unsupported designs stay with a separately declared
adapter. Tool installation is outside this helper.

```text
python3 scripts/run_count_de.py --counts COUNTS.tsv --metadata SAMPLES.tsv \
  --output NEW_REPORT.json --numerator TREATED --denominator CONTROL \
  --covariate BATCH_COLUMN --alpha 0.05 --min-count 10 --min-samples 3 \
  --fit-type local --independent-filtering enabled --cooks-cutoff enabled \
  --deseq2-version 1.52.0
```

Values above illustrate an explicitly chosen analysis, not scientific defaults.
Omit `--covariate` only when the declared design has no adjustment term.

## Workflow

1. Validate counts, sample alignment, replication and design rank.
2. Resolve the target contrast and blocking or batch terms from supplied facts; ask only when missing.
3. Fit one declared count model with recorded versions and settings.
4. Report effects, uncertainty, diagnostics, multiplicity and limitations.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- effect sizes, uncertainty, raw and adjusted significance
- design and contrast record
- QC, dispersion, outlier and confounding diagnostics

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Next outputs

For requested follow-up work, hand the completed result to the local identifier
mapping Skill, then choose ORA or complete-ranking GSEA according to the question.
Use the visualization Skill for figures and the reporting Skill for a source-linked
summary. Do not run every downstream step automatically when only DE was requested.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Require raw counts or a declared transcript-estimate import contract, sample alignment, biological replication, and an estimable full-rank design
- Declare the exact contrast, filtering, normalization, outlier, shrinkage, and multiplicity policy
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
