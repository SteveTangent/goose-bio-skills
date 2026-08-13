---
name: amplicon-beta-diversity-distance-analysis
description: "Use for bounded, offline pairwise beta-diversity distances from a local TSV containing exact amplicon feature rows, sample columns, and nonnegative integer counts. Calculate Bray-Curtis dissimilarity and presence/absence Jaccard distance for each stably sorted upper-triangle sample pair; return structured not-estimable metrics for every pair involving a zero-depth sample. Exclude FASTQ processing, denoising, rarefaction, normalization, ordination, PERMANOVA or other group comparison, differential abundance, taxonomy, pathogen decisions, and biological or clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.9.0"
---

# Amplicon Beta-Diversity Distance Analysis

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Owns

Calculate two descriptive distances for every unordered sample pair in one
already-produced feature-count table. Preserve integer counts and make no
normalization, adequacy, group-comparison, significance, taxonomy, pathogen,
biological, or clinical decision.

## Inputs and intake

Require one UTF-8 TSV and one new JSON output path, both resolving below the
current working directory. The first header must be `feature_id`; rows are
unique features and every remaining header is a unique sample ID containing
nonnegative integer counts. Require at least two samples.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **table-and-count-semantics.** Are rows exact amplicon features and cells
   unnormalized integer counts? Recommended: export the producer's feature-row
   count table unchanged; do not infer orientation or convert normalized values.
2. **distance-scope.** Does the request require only Bray-Curtis and binary
   Jaccard pairwise distances? Recommended: use this helper only for those
   descriptive distances; choose a study-specific workflow for ordination,
   group comparison, or inference.

An explicit local descriptive request authorizes the bounded read and one
create-new report when these facts are already supplied.

## Run

```text
python3 scripts/calculate_beta_distances.py \
  --feature-table FEATURE_COUNTS.tsv --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only. It refuses ambiguous orientation, duplicate or invalid IDs, fractional
or negative counts, excessive tables, depths, or sample pairs, parent traversal,
input/output symlinks, missing output parents, and existing outputs.

## Output contract

The deterministic JSON report binds the input fingerprint and fixed metric
definitions to stably sorted sample IDs and upper-triangle sample pairs. Each
metric includes `status`, exact integer `numerator` and `denominator`, and a
floating `value`. A pair involving any zero-depth sample instead returns both
metrics as `not-estimable` with reason `zero-depth-sample` and null numeric
fields. Read [format and metric boundaries](references/format-and-metric-boundaries.md).

## Guardrails

- Never infer orientation, feature identity, sample identity, count semantics,
  sampling adequacy, or cross-sample comparability.
- Never rarefy, normalize, transform, impute, filter, classify, or alter counts.
- Never perform ordination, PERMANOVA or other group comparison, differential
  abundance, taxonomy, contamination or pathogen decisions, or interpretation.
- Never overwrite, mutate input, create directories, follow symlinks, use the
  network, or start a subprocess.
- Require researcher review of producer semantics, depth differences, study
  design, and any downstream comparison.
