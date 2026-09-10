---
name: amplicon-feature-table-and-taxonomy-qc
description: "Check amplicon feature-count TSVs, sample metadata and optional taxonomy for structural consistency. Exclude filtering, diversity analysis, taxonomic assignment and contamination decisions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Amplicon Feature-table and Taxonomy QC

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


Detailed scope: Use for bounded, offline structural and descriptive QC of a local TSV amplicon feature-count table in explicit feature-rows-by-sample-columns orientation, exact sample metadata, and an optional rank-column taxonomy TSV. Report joins, library sizes, zero-depth samples, sparsity, feature totals, taxonomy-rank completeness, and declared negative controls. Exclude FASTQ processing, denoising, chimera removal, taxonomy assignment, BIOM/QZA parsing, diversity, differential abundance, contamination decisions, pathogen diagnosis, and clinical interpretation.

## Owns

Audit the structure and descriptive counts of one bounded local amplicon table,
sample metadata, and optional taxonomy. Preserve observed zeros as zeros and
make no contamination or biological-quality decision.

## Inputs and intake

Require UTF-8 TSV files and a new JSON output path:

- feature table: first header exactly `feature_id`; rows are features and all
  remaining columns are sample IDs containing nonnegative integer counts;
- metadata: one row per sample and an explicit sample-ID column, default
  `sample_id`;
- optional taxonomy: first header exactly `feature_id`, followed by one or more
  columns in canonical order from `domain`, `phylum`, `class`, `order`,
  `family`, `genus`, and `species`; blanks mean unassigned at that rank.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **table-orientation.** Which axis contains features and which contains samples? Recommended: export features as rows, sample IDs as columns, and name the first column `feature_id`; never infer a transposed table.
2. **negative-controls.** Which metadata column and exact values were declared as negative controls? Recommended: use producer-defined labels fixed before QC; omit these options when none were declared.

An explicit local QC request authorizes the bounded reads and new report.

## Run

```text
python3 scripts/qc_amplicon_tables.py \
  --feature-table FEATURE_COUNTS.tsv --metadata SAMPLE_METADATA.tsv \
  --output NEW_REPORT.json [--taxonomy TAXONOMY.tsv] \
  [--metadata-sample-column sample_id] \
  [--negative-control-column sample_type \
   --negative-control-value negative --negative-control-value blank]
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only. It refuses leaf symlinks, ambiguous orientation, invalid or duplicate
IDs, negative/fractional counts, taxonomy-ID mismatch, parent traversal,
symlinked output parents, and existing output paths. Fixed byte, row, column,
cell, identifier, and count caps are recorded in completed reports.

## Output contract

The create-new JSON report binds input fingerprints and exact declarations to:

- metadata/sample join counts and unmatched IDs;
- per-sample library sizes, zero-depth samples, total cells, zero cells, and
  sparsity;
- per-feature totals and zero-total features;
- optional per-rank assigned/unassigned taxonomy counts;
- declared negative-control sample library sizes and zero-depth status.

Duplicate-ID counters are zero in completed reports because duplicates fail
closed. Missing metadata joins are reported, while an optional taxonomy table
must cover exactly the feature IDs in the count table. Negative-control output
is descriptive and never a contamination conclusion.

## Guardrails

- Never infer table orientation, sample identity, taxonomy, control labels, or missing counts.
- Never treat zero as missing, normalize, rarefy, impute, classify, denoise, or alter counts.
- Never overwrite, mutate input, create directories, follow input/output symlinks, use the network, or start a subprocess.
- Exclude FASTQ, BIOM/QZA, diversity, differential abundance, contamination decisions, pathogen diagnosis, and clinical interpretation.
- Require researcher review of joins, producer semantics, and control behavior; this preview has no clinical or diagnostic authority.
