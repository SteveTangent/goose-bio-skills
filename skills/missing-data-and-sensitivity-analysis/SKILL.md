---
name: missing-data-and-sensitivity-analysis
description: "Describe missingness and sensitivity under explicit bounds or delta assumptions. Exclude automatic imputation, causal identification and inferential claims unsupported by design."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Bounded Missing-outcome Sensitivity

`Preview + reviewed`; the helper self-test passed. Agent runtime, scientific
benchmarking, and human-expert review were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use for a bounded local CSV/TSV with one continuous outcome when the user wants descriptive missingness, complete-case means, declared outcome-bound extremes, and an explicit delta sensitivity grid, optionally by a declared group column. Exclude missingness-mechanism inference, row-level imputation, model fitting, hypothesis testing, causal claims, and clinical use.

## Owns

Describe missing values in one continuous outcome and calculate transparent
aggregate sensitivity scenarios. This does not infer MCAR, MAR, or MNAR and
does not create an imputed dataset.

## Inputs and intake

Require a local UTF-8 CSV/TSV, outcome column, optional group column, declared
finite lower/upper outcome bounds, explicit comma-separated delta grid, and a
new JSON output path. Blank is missing; accept other tokens only when the user
declares their producer-specific meaning.

Inspect the header and request first. Ask one unresolved question with a
recommendation, then wait:

1. **outcome-and-group.** Which continuous outcome and optional grouping apply? Recommended: analyze one prespecified outcome and one prespecified grouping.
2. **missing-semantics.** Which exact tokens mean missing? Recommended: blank only unless the data producer documents additional tokens.
3. **bounds-and-grid.** What plausible outcome bounds and delta grid were chosen before viewing scenarios? Recommended: use protocol- or domain-anchored values and include zero explicitly.

An explicit local analysis request authorizes the bounded read and new report.

## Run

```text
python3 scripts/analyze_missing_outcomes.py \
  --input INPUT.csv --output NEW_REPORT.json --outcome-column outcome \
  [--group-column arm] --lower-bound 0 --upper-bound 100 \
  --delta-grid=-20,0,20 [--missing-token NA]
```

The dependency-free Python 3.10+ helper refuses leaf symlinks, unsafe output
paths, existing outputs, inputs over 16 MiB, more than 100,000 rows, 1,000
groups, 101 deltas, or 100,000 group-by-delta scenarios.

## Output contract

The create-new JSON report binds an input fingerprint and declared semantics to
overall and optional per-group row counts, missing fractions, complete-case
means, bound-extreme means, and delta scenarios. Delta means
`assumed missing-outcome mean = complete-case mean + delta`; it changes no
row-level value. A scenario outside declared bounds is reported as
`outside-declared-bounds`, and a group with no observed outcome is
`not-estimable-no-observed-values`.

## Guardrails

- Never infer MCAR, MAR, or MNAR from the observed missingness pattern.
- Never impute rows, fit a model, test a hypothesis, or interpret sensitivity as bias correction.
- Never guess missing tokens, bounds, grouping, or a delta grid.
- Never overwrite, mutate input, use the network, or start a subprocess.
- Require researcher review of outcome support, missing-value semantics, and scenario interpretation; this preview has no clinical or diagnostic authority.
