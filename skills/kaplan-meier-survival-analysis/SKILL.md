---
name: kaplan-meier-survival-analysis
description: "Estimate Kaplan-Meier survival from declared follow-up times and binary event indicators. Exclude log-rank tests, Cox models, competing risks and clinical recommendations."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Kaplan-Meier Survival Analysis

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


Detailed scope: Use for bounded, offline Kaplan-Meier summaries of a local subject-level TSV with one nonnegative follow-up time and one binary event indicator per subject, optionally split by an explicit group column. Produce deterministic product-limit estimates, median survival or not-reached status, and at-risk/event/censor counts. Exclude log-rank or other hypothesis tests, Cox or parametric models, confidence bands, delayed entry, recurrent or competing events, interval censoring, time-varying data, causal claims, treatment recommendations, and clinical interpretation.

## Owns

Summarize one already-prepared right-censored subject table. Report descriptive
Kaplan-Meier curves without choosing endpoints, redefining cohorts, or making
clinical, causal, superiority, or significance decisions.

## Inputs and intake

Require a UTF-8 TSV with exact headers `subject_id`, `time`, and `event`, plus
optional `group`. Require unique subjects, exact finite nonnegative decimal times, `event=1`
for the declared event and `event=0` for right censoring, and a new JSON path.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **endpoint-and-time-origin.** What protocol-defined event, time origin, and
   censoring rule do these fields represent? Recommended: export one prespecified
   endpoint with elapsed time from its declared origin; code only that event as
   `1` and valid right censoring as `0`.
2. **group-definition.** If grouped output is requested, what fixed cohort labels
   should be compared? Recommended: use labels defined before inspecting the
   survival outcome; do not derive groups from follow-up or event status.

An explicit local analysis request authorizes the bounded read and one
create-new report once these semantics are already supplied.

## Run

```text
python3 scripts/analyze_kaplan_meier.py \
  --input SUBJECTS.tsv --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files
only. It refuses malformed or extra columns, duplicate subjects, invalid times
or event codes, excessive rows/groups, parent traversal, symlinked input or
output parents, and existing outputs.

## Output contract

The deterministic JSON report binds the input fingerprint to:

- an overall curve and optional group curves with counts before each observed
  time, events, censors, and survival probability after events at that time;
- subject/event/censor totals and median survival, or explicit `not-reached`;
- descriptive group curves when a group column is present; no between-group
  hypothesis test or significance result.

Times are grouped and ordered as exact decimal values. Integral times are JSON
integers; non-integral times are canonical decimal strings, avoiding binary
floating-point collisions between distinct follow-up times.

Read [format and method boundaries](references/format-and-method-boundaries.md)
before interpreting ties or medians.

## Guardrails

- Never infer endpoints, time origins, censoring mechanisms, cohort labels, or
  whether censoring is non-informative.
- Never run log-rank or other hypothesis tests, fit Cox or parametric models,
  handle delayed entry, recurrent events,
  competing risks, interval censoring, time-varying rows, covariate adjustment,
  multiplicity, causal effects, or clinical decisions.
- Never turn a curve or median into a treatment recommendation,
  clinical claim, or automated significance/pass decision.
- Never overwrite, mutate inputs, create directories, follow symlinks, use the
  network, or start a subprocess.
- Require researcher review of endpoint semantics, cohort construction,
  censoring assumptions, and descriptive output.
