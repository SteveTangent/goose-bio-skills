---
name: two-group-log-rank-survival-comparison
description: "Use for one bounded, offline, two-sided Mantel-Cox log-rank comparison of exactly two prespecified nonempty groups in a local subject-level TSV with one exact nonnegative follow-up time and one binary event indicator per unique subject. Produce deterministic risk-set/event accounting, observed-minus-expected events, hypergeometric variance, a one-degree-of-freedom chi-square statistic, and an unadjusted p-value or structured not-estimable status. Exclude Kaplan-Meier curves or medians, more than two groups, stratified tests, Cox or parametric models, competing risks, delayed entry, multiplicity correction, significance decisions, clinical prediction, causal claims, and treatment recommendations."
license: Apache-2.0
metadata:
  version: "0.8.0"
---

# Two-Group Log-Rank Survival Comparison

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Owns

Compare the right-censored time-to-event distributions of exactly two already
prepared, prespecified groups with one unadjusted two-sided Mantel-Cox log-rank
test. Do not construct cohorts or make significance, clinical, causal, or
treatment decisions.

## Inputs and intake

Require a UTF-8 TSV with exact headers `subject_id`, `time`, `event`, and
`group`. Require unique subjects, exactly two nonempty group labels, exact
finite nonnegative decimal times, and `event=1` for the declared event or
`event=0` for valid right censoring. Require a new JSON output path.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **endpoint-and-time-origin.** What prespecified event, time origin, unit, and
   censoring rule do the fields represent? Recommended: export one endpoint
   with elapsed time from its declared origin; code only that event as `1` and
   valid right censoring as `0`.
2. **group-definition.** Which two labels are the fixed comparison groups?
   Recommended: use groups defined before inspecting outcomes; the helper
   reports the lexicographically first label as group A only to make the
   observed-minus-expected direction deterministic.

An explicit local comparison request authorizes the bounded read and one
create-new report once these semantics are already supplied.

## Run

```text
python3 scripts/compare_log_rank.py \
  --input SUBJECTS.tsv --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only below the current working directory. It rejects malformed or extra columns, duplicate subjects, invalid
times/events, other-than-two groups, oversized input, parent traversal,
symlinked input or output parents, and existing outputs.

## Output contract

The deterministic JSON report binds the input SHA-256 to:

- group labels and subject/event/censor totals;
- each event time's two-group risk set, events, same-time censors, exact
  expected group-A events, observed-minus-expected values, and exact
  hypergeometric variance;
- exact rational observed-minus-expected and total variance values;
- a one-degree-of-freedom chi-square statistic and unadjusted two-sided
  `erfc(sqrt(chi_square / 2))` p-value, `underflow` with a null p-value when the
  finite tail is below the supported float range, or `not-estimable` when
  variance is zero.

Exact rationals carry integer numerator and denominator plus a convenience
float. The final p-value uses the platform C math library, so the last binary
floating-point digit is not promised across platforms; a finite tail is never
reported as an exact zero. No threshold or significance decision is emitted.

Read [format and method boundaries](references/format-and-method-boundaries.md)
before interpreting ties, censoring, or a not-estimable result.

## Guardrails

- Never infer endpoints, time origins, censoring mechanisms, group definitions,
  or whether censoring is non-informative.
- Never emit Kaplan-Meier curves or medians, compare more than two groups, run
  stratified or weighted tests, fit Cox or parametric models, handle delayed
  entry, recurrent or competing events, adjust for multiplicity, or predict
  clinical outcomes.
- Never convert the p-value into an automated significance, pass/fail, causal,
  superiority, treatment, or clinical decision.
- Never overwrite, mutate inputs, create directories, follow symlinks, use the
  network, or start a subprocess.
- Require researcher review of endpoint, cohort, censoring, and model
  assumptions before interpretation.
