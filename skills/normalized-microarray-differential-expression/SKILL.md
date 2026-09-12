---
name: normalized-microarray-differential-expression
description: "Compare two independent groups in one already-normalized log2 microarray matrix. Exclude raw counts, TPM/FPKM, paired designs, probe collapsing and normalization."
license: Apache-2.0
metadata:
  version: "0.12.0"
---

# Normalized Microarray Differential Expression

`Preview + reviewed`. Basic local execution is checked; Agent behavior, representative scientific benchmarks and human expert review remain unverified.

## Use

One normalized log2 microarray matrix and sample table need a declared numerator-versus-denominator contrast. Retain whether rows represent probes or genes. Raw counts belong to count-based differential expression; protein abundance belongs to its own adapter.

## Interaction

Inspect supplied files and existing facts first. Follow [the dialogue guide](references/user-dialogue.md): ask only the most consequential unresolved question, explain why it matters, and wait on dependent analysis. Never infer normalization, biological independence or group labels from number ranges or filenames. With complete facts and authorized local inputs, proceed.

## Run and deliver

Read [the local adapter](references/local-adapter.md) before using `scripts/run_microarray_de.py`. Confirm platform, taxon, identifier namespace, normalization provenance, independent subjects, contrast and any categorical adjustment. Preserve original inputs and write a new result directory.

Deliver the effect, pointwise confidence interval, moderated t statistic, raw p-value and BH-adjusted p-value for every input feature; retain sample PCA, correlations, design diagnostics, versions and warnings. Use the existing visualization and reporting Skills for figures and interpretation. Use explicit mapping before gene-set analysis; do not count multiple probes as independent genes or silently pick a probe.

## Limits and failures

Missing facts yield `needs-decision`; incompatible data or design stop before publication; a missing or mismatched R/limma environment yields `needs-tool`. No automatic normalization, imputation, sample deletion, final biological interpretation or clinical decision. See [runtime boundaries](references/runtime-boundaries.md). Two samples per group is a computational minimum, not a sample-size recommendation.
