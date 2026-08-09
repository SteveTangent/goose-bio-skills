---
name: pairwise-and-multiple-sequence-alignment
description: "A user needs global, local or multiple alignment of an existing sequence set. Exclude: database similarity search; tree inference; asserting positional homology without qualification."
---

# Pairwise and Multiple Sequence Alignment

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce an alignment fit for a declared downstream purpose and report sensitivity to key alignment choices. Exclusions are declared in the trigger above.

## Inputs

- validated sequence records
- alignment objective
- sequence type and expected divergence

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **alignment-objective.** Which downstream question must the alignment support? Recommended: Select local, global or multiple alignment from the declared downstream question.

## Workflow

1. Check sequence type, count, length and divergence clues.
2. Select global, local or multiple alignment based on the stated objective.
3. Run with recorded parameters and stable input ordering.
4. Report coverage, gaps, unstable regions and downstream-use limitations.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- alignment artifact
- method, version and parameter record
- alignment statistics and low-confidence regions

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Separate pairwise from multiple alignment and declare nucleotide or protein input
- Declare global or local objective, scoring matrix, gap penalties, strategy, threads, seed if present, and input order
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
