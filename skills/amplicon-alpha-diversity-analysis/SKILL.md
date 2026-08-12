---
name: amplicon-alpha-diversity-analysis
description: "Use for bounded, offline per-sample alpha-diversity summaries from a local TSV containing exact amplicon feature rows, sample columns, and nonnegative integer counts. Calculate observed features, natural-log Shannon diversity, and Simpson diversity defined as one minus the sum of squared relative abundances; return explicit not-estimable results for zero-depth samples. Exclude FASTQ processing, denoising, rarefaction, normalization, compositional correction, beta diversity, hypothesis testing, differential abundance, taxonomy, contamination or pathogen decisions, and biological or clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Amplicon Alpha Diversity Analysis

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Owns

Calculate three descriptive alpha-diversity metrics for each sample in one
already-produced feature-count table. Preserve integer counts and make no
comparability, adequacy, significance, contamination, or biological decision.

## Inputs and intake

Require one UTF-8 TSV and a new JSON output path. The first header must be
`feature_id`; rows are unique features and every remaining header is a unique
sample ID containing nonnegative integer counts.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **table-and-count-semantics.** Are rows exact amplicon features and cells
   unnormalized integer counts? Recommended: export the producer's feature-row
   count table unchanged; do not infer orientation or convert normalized values.
2. **cross-sample-comparability.** Is the user asking only for per-sample
   descriptions, or for cross-sample inference? Recommended: use this helper
   only for descriptive values; stop and choose a study-specific method before
   comparing groups or unequal-depth samples.

An explicit local descriptive request authorizes the bounded read and one
create-new report when these facts are already supplied.

## Run

```text
python3 scripts/calculate_alpha_diversity.py \
  --feature-table FEATURE_COUNTS.tsv --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only. It refuses ambiguous orientation, duplicate or invalid IDs, fractional
or negative counts, excessive tables or depths, parent traversal, input/output
symlinks, missing output parents, and existing outputs.

## Output contract

The deterministic JSON report binds the input fingerprint and fixed metric
definitions to feature/sample counts and, for every sample:

- total depth;
- observed-feature count;
- Shannon diversity with natural logarithms;
- Simpson diversity as `1 - sum(p_i^2)`.

All three metrics are structured `not-estimable` with reason `zero-depth` when
the sample total is zero. Read [format and metric boundaries](references/format-and-metric-boundaries.md).

## Guardrails

- Never infer orientation, feature identity, sample identity, count semantics,
  sampling adequacy, or cross-sample comparability.
- Never rarefy, normalize, impute, transform, filter, classify, or alter counts.
- Never compute beta diversity, group tests, differential abundance, taxonomy,
  contamination or pathogen decisions, or biological/clinical interpretation.
- Never overwrite, mutate input, create directories, follow symlinks, use the
  network, or start a subprocess.
- Require researcher review of producer semantics, depth differences, study
  design, and any downstream comparison.
