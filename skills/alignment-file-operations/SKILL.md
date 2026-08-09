---
name: alignment-file-operations
description: "A user needs metadata inspection, sorting, indexing, region extraction, filtering or basic query operations on SAM/BAM/CRAM. Exclude: aligning raw reads; variant calling; assuming a missing or mismatched reference."
license: Apache-2.0
metadata:
  version: "0.2.1"
---

# Alignment File Operations

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Perform bounded, auditable operations on existing alignment files without changing biological meaning silently. Exclusions are declared in the trigger above.

## Inputs

- alignment file
- reference and build for CRAM or coordinate queries
- requested operation and filter semantics

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **alignment-reference.** Which exact reference identity governs this alignment file? Recommended: Require the reference digest or immutable release, especially for CRAM.
2. **alignment-sort-order.** Which sort order does the requested operation require? Recommended: Use coordinate order for indexed region queries and name order only for operations that require read pairing.

## Workflow

1. Inspect format, header, sort order, index and reference identity.
2. Translate the requested operation into explicit flag and coordinate semantics.
3. Run read-only checks before creating any output artifact.
4. Validate counts, headers and indexability of the result.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- operation result or dry-run command plan
- header, reference and index checks
- record-count and filtering audit

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Bind every operation to the exact reference assembly, sequence dictionary, and reference digest
- Declare sort order, index state, region coordinate semantics, MAPQ, secondary, supplementary, and duplicate policies
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
