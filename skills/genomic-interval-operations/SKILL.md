---
name: genomic-interval-operations
description: "A user needs same-build interval overlap, merge, subtraction, nearest-feature or coordinate-convention operations. Exclude: cross-build lift-over or chain-file mapping; variant normalization; assuming coordinate conventions or tool parity without evidence."
license: Apache-2.0
metadata:
  version: "0.4.0"
---

# Genomic Interval Operations

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Apply deterministic same-build interval algebra under an auditable coordinate contract. Exclusions are declared in the trigger above.

## Inputs

- interval files or tables
- reference build and contig naming
- zero- or one-based and closed or half-open convention
- strand policy

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **interval-build.** Which reference build governs these intervals? Recommended: Require one exact same-build reference; cross-build lift-over is outside this Skill.
2. **interval-convention.** Which coordinate convention governs these intervals? Recommended: Require explicit zero/one-based and closed/half-open semantics before interval algebra.

## Workflow

1. Declare build, contig, coordinate and strand semantics.
2. Validate intervals for ordering, bounds and malformed records.
3. Apply one explicit interval operation.
4. Check boundary cases and report transformations and dropped records.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- result intervals
- declared coordinate and strand contract
- counts, unmapped contigs and boundary warnings

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Declare assembly, contig dictionary and order, zero- or one-based origin, half-open or closed intervals, and strand policy
- Define bookended merge, nearest-tie, overlap, and missing-contig behavior before execution
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
