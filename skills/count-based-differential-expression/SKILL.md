---
name: count-based-differential-expression
description: "A user has integer-like counts plus sample metadata and needs a group or covariate differential-expression analysis. Exclude: FASTQ-to-count processing; pathway enrichment; assuming two software adapters are numerically identical."
license: Apache-2.0
metadata:
  version: "0.4.1"
---

# Count-based Differential Expression

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Estimate a declared contrast from counts with a defensible design, diagnostics and multiple-testing record. Exclusions are declared in the trigger above.

## Inputs

- feature-by-sample count matrix
- sample metadata
- design formula and target contrast
- filtering and independent-filter policy

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **primary-contrast.** What is the primary differential-expression contrast? Recommended: Declare one estimable contrast before fitting the model.

## Workflow

1. Validate counts, sample alignment, replication and design rank.
2. Confirm the target contrast and blocking or batch terms.
3. Fit one declared count model with recorded versions and settings.
4. Report effects, uncertainty, diagnostics, multiplicity and limitations.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- effect sizes, uncertainty, raw and adjusted significance
- design and contrast record
- QC, dispersion, outlier and confounding diagnostics

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Require raw counts or a declared transcript-estimate import contract, sample alignment, biological replication, and an estimable full-rank design
- Declare the exact contrast, filtering, normalization, outlier, shrinkage, and multiplicity policy
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
