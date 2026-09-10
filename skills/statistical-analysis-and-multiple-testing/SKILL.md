---
name: statistical-analysis-and-multiple-testing
description: "Adjust declared families of raw p-values using BH or Holm and report the chosen error-control assumptions. Exclude inventing tests, automatic family selection and arbitrary-dependence FDR guarantees."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Offline BH or Holm Correction

`Preview + reviewed`; runtime, benchmark, expert, and clinical validation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use when a table contains raw p-values, every hypothesis belongs to an explicitly declared family, and the user wants offline Benjamini-Hochberg FDR or Holm FWER correction. Exclude model fitting, effect estimation, raw-count differential expression, enrichment, prospective design, undeclared families, and arbitrary-dependence FDR methods.

## Owns

Correct raw p-values in declared families with BH (`bh`) or Holm (`holm`),
without fitting a model or inferring families from results.

## Inputs

- local CSV/TSV with unique IDs and finite p-values in `[0,1]`
- the complete family membership, declared before correction
- `bh` under its dependence conditions, or `holm` for FWER
- an optional alpha in `(0,1)` only when a reject/not-reject decision is wanted,
  plus a new result path and an optional validation-report path

## Intake

Inspect the table and request first. Ask one unresolved question with a
recommendation, then wait. Do not run with unresolved families or objective;
neither method supplies arbitrary-dependence FDR control.

Decision order:

1. **multiplicity-family.** Which hypotheses form each complete family? Recommended: declare it before viewing adjusted results.
2. **error-control-method.** Use BH FDR or Holm FWER? Recommended: BH only under its conditions; Holm for FWER.
3. **alpha.** If reject/not-reject labels are requested, which protocol alpha applies? Recommended: supply it explicitly; otherwise return adjusted p-values without a decision column.

## Run

Use the dependency-free Python 3.10+ helper:

```text
python3 scripts/adjust_pvalues.py --input INPUT --output OUTPUT \
  --method bh|holm [--alpha 0.05] [--validation-output VALIDATION.json] \
  --id-column record_id --p-column p_value [--family-column family_id]
```

It validates before publishing, preserves row order and other columns, handles
each family separately, and adds `p_adjusted`; it adds `decision` only when
`--alpha` is supplied. The optional validation path receives a structured
invalid-input report. It refuses
existing outputs, unsafe paths, symlink/non-regular inputs, inputs over 16 MiB,
tables over 100,000 rows, and unselected `family_id`. Larger batches return
`needs-tool`. Read [method boundaries](references/multiplicity-methods.md).

## Output contract

Return `completed` only when the new result exists and all rows were processed.
Invalid input returns `invalid-input` and, when possible, only the requested
validation artifact with `analysis_performed=false`. Missing choices are
`needs-decision`; unsupported work is `needs-tool` or `dry-run`.

## Guardrails

- Never mutate/overwrite, pool undeclared families, or invent results.
- The [permission policy](security/permission_policy.json) approves only create-exclusive helper outputs below the current working directory; network and subprocess use are forbidden.
- Record method, optional alpha, families, Python version, input fingerprint, warnings, and limits.
- Require researcher review for family definition and interpretation; never use this preview for clinical or diagnostic decisions.
