---
name: statistical-analysis-and-multiple-testing
description: "Use when a table contains raw p-values, every hypothesis belongs to an explicitly declared family, and the user wants offline Benjamini-Hochberg FDR or Holm FWER correction. Exclude model fitting, effect estimation, raw-count differential expression, enrichment, prospective design, undeclared families, and arbitrary-dependence FDR methods."
license: Apache-2.0
metadata:
  version: "0.6.0"
---

# Offline BH or Holm Correction

`Preview + reviewed`; runtime, benchmark, expert, and clinical validation were not performed.

## Owns

Correct raw p-values in declared families with BH (`bh`) or Holm (`holm`),
without fitting a model or inferring families from results.

## Inputs

- local CSV/TSV with unique IDs and finite p-values in `[0,1]`
- the complete family membership, declared before correction
- `bh` under its dependence conditions, or `holm` for FWER
- an explicit alpha in `(0,1)` and new result/validation paths under the current directory

## Intake

Inspect the table and request first. Ask one unresolved question with a
recommendation, then wait. Do not run with unresolved families or objective;
neither method supplies arbitrary-dependence FDR control.

Decision order:

1. **multiplicity-family.** Which hypotheses form each complete family? Recommended: declare it before viewing adjusted results.
2. **error-control-method.** Use BH FDR or Holm FWER? Recommended: BH only under its conditions; Holm for FWER.
3. **alpha.** Which protocol alpha applies? Recommended: supply it explicitly; use 0.05 only when declared.

## Run

Use the dependency-free Python 3.10+ helper:

```text
python3 scripts/adjust_pvalues.py --input INPUT --output OUTPUT \
  --validation-output VALIDATION.json --method bh|holm --alpha 0.05 \
  --id-column record_id --p-column p_value [--family-column family_id]
```

It validates before publishing, preserves row order and other columns, handles
each family separately, and adds `p_adjusted` and `decision`. It refuses
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
- Record method, alpha, families, Python version, input fingerprint, warnings, and limits.
- Require researcher review for family definition and interpretation; never use this preview for clinical or diagnostic decisions.
