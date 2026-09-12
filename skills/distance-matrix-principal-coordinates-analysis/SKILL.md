---
name: distance-matrix-principal-coordinates-analysis
description: "Run classical PCoA on an existing complete sample distance matrix or native beta-diversity distances, retaining negative eigenvalues. Exclude abundance preprocessing, PCA, PERMANOVA and group inference."
license: Apache-2.0
metadata:
  version: "0.13.0"
---

# Distance Matrix Principal Coordinates Analysis

Preview + reviewed. Small helper checks do not establish representative scientific
performance, Agent routing accuracy or human expert review.

## Inputs and interaction

Use safely inspected facts first. Require an existing local distance matrix,
sample IDs, declared distance metric and optional sample_id/group metadata.
Do not guess what distance a matrix contains. Ask one consequential question at
a time, explain the term that changes the decision, and wait on dependent work.
With complete facts and authorized safe local execution, proceed without repeat
confirmation. Keep the host's permission boundary for new side effects.

- PCoA represents distances; PCA starts from a feature matrix. Do not substitute one for the other.
- If native pairs are undefined because of zero-depth samples, request the upstream sample decision; never fill missing distances.
- Explain that visual group separation is exploratory, not a significant group difference.

## Execution and outputs

Use [run_pcoa.py](scripts/run_pcoa.py) for 3–128 samples and at most 8 MiB per
input. It validates a complete symmetric nonnegative matrix, exact zero diagonal
and one-to-one sample identity. It does not transform, normalize or correct the
input distances. See [formats and examples](references/local-adapter.md).

Deliver a new directory with pcoa.json, coordinates.tsv and eigenvalues.tsv.
Retain every signed eigenvalue, numerical tolerance, both positive and absolute
inertia denominators, negative-axis coordinates and the error from reconstructing
distances using positive axes. Unknown input decisions return needs-decision;
invalid matrices return invalid-input; missing NumPy returns needs-tool.

Use bioinformatics-result-visualization with --kind pcoa for PNG/SVG plus plotted
data, and bioinformatics-qc-and-publication-reporting for delivery. Present the
figure with its metric, denominator and negative-inertia caveat. A one-dimensional
result explicitly pads the display's second axis with zero.

## Boundaries

No raw-count preprocessing, rarefaction, abundance transformation, correction of
negative eigenvalues, PERMANOVA, dispersion tests, differential abundance,
taxonomy, biological causal claims or clinical interpretation. An all-zero
matrix has no informative ordination. No network, input mutation or overwrites.
The producer's distance semantics and suitability remain researcher decisions.
