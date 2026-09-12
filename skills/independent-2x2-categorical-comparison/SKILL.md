---
name: independent-2x2-categorical-comparison
description: "Compare one independent 2x2 integer count table with a two-sided Fisher exact test and conditional odds ratio confidence interval. Exclude paired data, repeated subjects, weights, regression and population risk estimation."
license: Apache-2.0
metadata:
  version: "0.14.0"
---

# Independent 2×2 Categorical Comparison

Preview + reviewed; small helper checks do not imply representative scientific
validation, Agent behavior evaluation or human expert review.

## Input and interaction

Inspect the table first. Require two group labels, mutually exclusive event and
non-event meanings, independent observations and sampling design. Preserve row,
column and denominator meaning. Ask the first unresolved consequential question,
explain why it changes the analysis, and wait on dependent work. Fully specified,
authorized local work proceeds without repeated confirmation.

Correct evidenced misconceptions: odds ratio is not risk ratio; case-control row
fractions are not population risks; paired before/after records require a paired
method. Do not add 0.5 just to make a zero cell disappear. Keep host permissions
for new side effects; no network or input mutation is performed.

## Execution and output

Use [compare_2x2.py](scripts/compare_2x2.py), with
[formats and methods](references/local-adapter.md). A TSV table has group, event,
non_event and exactly two rows. Counts are nonnegative integers with at most
100,000 total observations. Use a trusted SciPy 1.17.1 environment; another or
missing version returns needs-tool. The deterministic schema/I/O self-test does
not require SciPy; numerical checks are recorded separately.

Deliver a new directory with comparison.json and counts.tsv. State:

- the exact event-odds direction, numerator group versus denominator;
- two-sided Fisher p-value using fixed-margin probability ordering;
- conditional maximum-likelihood odds ratio and conditional exact equal-tailed interval;
- the separate sample cross-product odds ratio, without confusing estimates;
- zero/infinite estimates or bounds without hidden continuity correction.

An empty row/column, unknown sampling design or unresolved independence yields
needs-decision and no inferential result. Invalid data return invalid-input.
Reuse bioinformatics-result-visualization (--kind categorical) for observed-count
plots and the shared report for a concise interpretation with sample denominators.

## Limits

One prespecified table only. No paired/repeated data, survey weights, stratified
inference, regression, causal claims, population risk/risk-difference estimates,
clinical decisions or adjustment across a collection of tests. Fisher's two-sided
ordering differs from equal-tailed interval inversion, so a p-value threshold and
whether the interval excludes one need not agree exactly. Researchers still judge
sampling assumptions and biological meaning; significance is not importance.
