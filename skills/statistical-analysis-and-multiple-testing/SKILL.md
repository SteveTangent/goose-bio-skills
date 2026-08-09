---
name: statistical-analysis-and-multiple-testing
description: "Use when a table contains raw p-values, every hypothesis belongs to an explicitly declared family, and the user wants offline Benjamini-Hochberg FDR or Holm FWER correction. Exclude model fitting, effect estimation, raw-count differential expression, enrichment, prospective design, undeclared families, and arbitrary-dependence FDR methods."
---

# Offline BH or Holm Correction

`Preview + reviewed`; agent runtime, scientific benchmark, human-expert review,
and clinical validation were not performed.

## Owns

Correct raw p-values within caller-declared families using ordinary
Benjamini-Hochberg (`bh`) or Holm (`holm`). This Skill does not choose or fit an
upstream statistical model and does not infer family membership from results.

## Inputs

- a local CSV or TSV with unique non-empty record IDs and finite p-values in `[0,1]`
- the complete family membership, declared before correction
- `bh` for FDR under independence or suitable positive dependence, or `holm` for FWER
- an explicit alpha in `(0,1)` and new result/validation paths under the current directory

## Intake

Inspect the table, requested method, alpha, families, and output paths first. If
one result-changing choice is missing, ask exactly one question with a
recommendation and wait. Do not run while family membership or the error-control
objective is unresolved. Neither bundled method supplies arbitrary-dependence
FDR control.

## Run

Use the dependency-free Python 3.10+ helper:

```text
python3 scripts/adjust_pvalues.py --input INPUT --output OUTPUT \
  --validation-output VALIDATION.json --method bh|holm --alpha 0.05 \
  --id-column record_id --p-column p_value [--family-column family_id]
```

It validates the complete table before publishing, preserves input row order
and non-key columns, applies each declared family separately, and adds
`p_adjusted` and `decision`. It refuses existing outputs, parent traversal,
symlink parents, an unselected `family_id`, and all result creation after invalid
input. Read [method boundaries](references/multiplicity-methods.md) before
interpreting the correction.

## Output contract

Return `completed` only when the new result exists and all rows were processed.
For invalid input, return `invalid-input`, create only the requested validation
artifact when possible, and set `analysis_performed=false`. Missing choices are
`needs-decision`; unsupported execution is `needs-tool` or `dry-run`. Partial
output is never `completed`.

## Guardrails

- Never mutate inputs, overwrite any path, pool undeclared families, or invent effects, intervals, diagnostics, or biological conclusions.
- The [permission policy](security/permission_policy.json) approves only create-exclusive helper outputs below the current working directory; network and subprocess use are forbidden.
- Record method, alpha, family definition, Python version, input fingerprint, warnings, and limitations.
- Require researcher review for family definition and interpretation; never use this preview for clinical or diagnostic decisions.
