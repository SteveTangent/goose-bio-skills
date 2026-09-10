---
name: evidence-synthesis-and-research-traceability
description: "Synthesize an identified biomedical evidence corpus with claim-to-source traceability and uncertainty. Exclude primary literature discovery and clinical decision authority."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Evidence Synthesis and Research Traceability

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user has a defined corpus or retrieval record and needs comparison, synthesis, conflict handling or research traceability. Exclude: unlogged corpus expansion; majority vote over conflicting evidence; clinical advice without governed specialist review.

## Owns

Produce a transparent evidence synthesis in which every material claim maps to appropriate sources and dissent remains visible. Apply the detailed scope below.

## Inputs

- bounded evidence corpus
- claim or review questions
- inclusion criteria and evidence hierarchy
- citation and traceability requirements

## Intake

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

Decision order:

1. **evidence-hierarchy.** Which hierarchy governs conflicts? Recommended: define it before synthesis and separate community signals.
2. **claim-criteria.** What supports a material claim? Recommended: predeclare inclusion, contradiction, and uncertainty rules.

## Public network execution

An explicit citation check authorizes bounded public/polite `crossref-rest`
lookups for records already in the frozen corpus. Do not expand the corpus or
use a paid fallback. Confirm sensitive material or unrequested bulk. Preserve
unresolved citations on failure and record provider, access time, request
digest, response status, and network use.

## Workflow

1. Freeze the corpus and synthesis questions.
2. Extract claims, methods, populations and limitations without losing source identity.
3. Map support and conflict under an explicit evidence hierarchy.
4. Resolve included-record metadata when needed, then report qualified conclusions, dissent, missing evidence and traceability links.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- claim-to-source graph or table
- evidence-quality and conflict summary
- qualified conclusions, gaps and excluded evidence

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). DOI metadata lookup
does not validate evidence quality or support a scientific claim.

## Guardrails

- Accept only a frozen corpus with a retrieval record and stable identifiers; if absent, return a retrieval handoff and do not search silently
- Map each material claim to sources at appropriate granularity and preserve support, conflict, uncertainty, and missing evidence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
