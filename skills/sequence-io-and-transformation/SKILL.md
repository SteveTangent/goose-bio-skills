---
name: sequence-io-and-transformation
description: "A user requests deterministic sequence conversion or transformation after validation-only preflight. Exclude: validation-only inspection without transformation; database similarity search; pairwise or multiple sequence alignment; functional annotation from sequence alone."
license: Apache-2.0
metadata:
  version: "0.4.0"
---

# Sequence I/O and Transformation

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Read, transform and write sequence records with explicit loss and round-trip checks. Exclusions are declared in the trigger above.

## Inputs

- sequence files or records
- declared alphabet and genetic code when relevant
- requested transformation and output format

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **sequence-alphabet.** Which sequence alphabet should govern parsing? Recommended: Use the declared alphabet; infer only when the input is unambiguous and report the inference.
2. **translation-code.** Which genetic code should translation use? Recommended: Use the explicitly declared organism-appropriate code rather than the universal code by assumption.
3. **metadata-preservation.** Which record metadata must the transformed output preserve? Recommended: Preserve identifiers, ordering and quality values whenever the target format supports them.

## Workflow

1. Validate format, alphabet, identifiers and qualities.
2. Apply only the requested deterministic transformation.
3. Preserve ordering and metadata unless the brief says otherwise.
4. Re-read outputs and report any lossy conversion.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- transformed sequence artifact or dry-run plan
- record counts and rejected records
- round-trip and information-loss report

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Declare input and output formats, alphabet, quality encoding, genetic code, frame, and identifier policy when applicable
- Report metadata or quality information lost by a conversion
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
