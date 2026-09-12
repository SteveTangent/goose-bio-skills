---
name: qpcr-relative-expression-and-qc
description: "Check one-run RT-qPCR Cq tables and calculate within-target relative expression using declared amplification factors and reference assays. Exclude raw curves, DNA copy number, imputation, reference selection and group significance testing."
license: Apache-2.0
metadata:
  version: "0.14.0"
---

# qPCR Relative Expression and QC

Preview + reviewed. Small original helper checks are separate from scientific
benchmarking, Agent behavior evaluation and human expert review.

## Input and dialogue

Inspect available Cq, sample and assay files before asking. Require sample to
subject/group mapping, one run, target/reference roles, assay amplification factors,
validated quantitative Cq ranges and a short design record. With complete facts
and authorized local execution, proceed without repeat confirmation.

Ask one consequential question at a time, with why it matters and the minimum
useful record; wait on dependent work. Explain only terms that change the decision:
Cq is a cycle threshold, not abundance; amplification factor 2 means 100% per-cycle
efficiency; technical wells are not independent biological subjects. Do not assume
reference genes are stable or that undetermined means zero expression. Preserve
host permissions for any new side effect; no network is used by the core helper.

## Execution and delivery

Use [analyze_qpcr.py](scripts/analyze_qpcr.py) with the
[local adapter contract](references/local-adapter.md). The standard-library path
supports one run, 4–32 independent samples, 2–4 groups, 1–8 targets, 1–3 justified
references, and 2–4 technical wells per sample/assay. Inputs are at most 8 MiB each.

Check technical repeat ranges, detection status, declared quantification limits,
reference coverage and independent subjects. Report unresolved facts as
needs-decision with technical QC; do not produce relative quantities until resolved.
Invalid schema returns invalid-input; existing outputs are never overwritten.

Average Cq within each sample/assay. Use efficiency-corrected quantities; the
2^-ΔΔCq shortcut is available only with explicit factor-2 validation for every
assay. Normalize by the geometric mean of reference quantities, then to the
calibrator group's geometric mean. Preserve calculation settings and original
input digests. Deliver qpcr.json, technical-qc.tsv and, when complete,
relative-expression.tsv and group-summary.tsv.

Plot one chosen target through bioinformatics-result-visualization (--kind qpcr,
--outcome TARGET). Show one point per subject on a declared log2-relative scale,
and include the shared Chinese/English report. Clarify that fold changes compare
within a target, not absolute expression between different target assays.

## Limits

No raw fluorescence fitting, automatic control/reference selection, missing or
censored-value substitution, outlier deletion, cross-run calibration, repeated
subjects, absolute DNA copy number, group test, clinical interpretation or MIQE
certification. Efficiency/calibrator uncertainty and prediction intervals are not
propagated; this is a bounded point-estimate/QC path. User review of assay controls,
reference suitability and biological plausibility remains necessary.
