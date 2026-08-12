---
name: proteomics-quantification-table-qc
description: "Use for QC of an already quantified peptide-, protein-group-, or protein-abundance table and sample metadata. Check missingness, duplicates, scale, and design readiness. Exclude raw MS, identification/FDR, protein inference, normalization, imputation, modeling, and clinical use."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Proteomics Quantification Table QC

`Preview + reviewed`; large-table and R/Bioconductor execution were not performed.

## Scope and inputs

Report readiness for one quantified peptide-, protein-group-, or protein-level
table and its sample design. Do not identify, normalize, impute, or model.

Require:

- a bounded delimited table or declared quantitative object;
- sample metadata, intended comparison, replicate and batch fields;
- feature level, identifiers, sample join keys, unit, scale, and normalization state;
- declared meanings of blank, missing, zero, negative, and censored values.

Inspect headers, schema, and a bounded sample first. An explicit local request
authorizes safe reads and a new report. Ask one question at a time only when a
result-changing choice remains, in this order:

1. **feature-boundary:** peptide or protein? Recommend one declared level; route PSMs and mixed levels elsewhere.
2. **missing-zero-semantics:** what do blanks, zeros, negatives, and censored values mean? Preserve producer semantics.
3. **sample-design:** which columns map to samples, replicates, conditions, batches, and contrast? Freeze a one-to-one join before modeling.

## Workflow

1. Preflight size; for large inputs use `scientific-file-preflight-and-resource-planning` and skip unsupported full scans.
2. Verify feature level, unit, scale, normalization state, identifiers, and sample joins without guessing from filenames.
3. Check dimensions, duplicate or empty IDs, duplicate sample keys, mixed levels, non-numeric or infinite cells, negatives, and metadata disagreement.
4. Summarize declared missingness and observed distributions; report replication, confounding, scale ambiguity, provenance gaps, and outliers for researcher review.

## Result and boundaries

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. A completed report binds the inspected scope, table dimensions,
feature level, joins, duplicate/value findings, missing/zero summaries,
distribution warnings, design blockers, assumptions, and skipped checks.

- Never recode zero as missing without declared semantics.
- Never mix PSM, peptide, protein-group, and protein rows.
- Do not silently choose or run normalization, imputation, batch correction, differential abundance, or multiplicity correction.
- Route raw spectra, search, PEP/q-value/FDR, and protein inference elsewhere; route inferential multiplicity to `statistical-analysis-and-multiple-testing`.
- Use no network service, upload no table, and never overwrite or mutate inputs.
- Skipped R/Bioconductor or large-table work remains `partial` or `needs-tool`, never passed.

See [runtime boundaries](references/runtime-boundaries.md) for reviewed interfaces and unverified behavior.
