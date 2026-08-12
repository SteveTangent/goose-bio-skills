---
name: experimental-design-power-and-batch-planning
description: "A user needs sample-size, allocation, blocking, randomization or confounding review for a biological study. Exclude: claiming analysis can repair complete confounding; physical wet-lab execution or instrument operation; using a generic formula where assay-specific distribution is load-bearing."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Experimental Design, Power and Batch Planning

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce a feasible, auditable design that separates the primary contrast from known batches and states power assumptions. Exclusions are declared in the trigger above.

## Inputs

- primary objective and contrast
- plausible effect and variance assumptions
- candidate sample and batch structure
- constraints and dropout expectations

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **design-primary-contrast.** What is the primary prospective contrast? Recommended: Choose one primary estimand before allocating samples.
2. **minimum-meaningful-effect.** What minimum effect would be scientifically meaningful? Recommended: Use a plausible domain-informed effect and show sensitivity rather than a single optimistic value.

## Workflow

1. Define one primary contrast and estimand.
2. Inspect replication, exchangeability, batch structure and constraints.
3. Evaluate design rank and power or precision across plausible assumptions.
4. Recommend allocation, randomization and sensitivity checks with irreparable confounding explicit.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- design and allocation proposal
- power or precision curve with assumptions
- design-matrix rank and confounding findings

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Declare estimand, outcome model, independent unit, meaningful effect, variance source, alpha, power or precision target, dropout, allocation, and budget
- Check design-matrix rank and prevent treatment, batch, site, or processing order from becoming confounded
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
