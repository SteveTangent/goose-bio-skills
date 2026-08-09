---
name: evidence-synthesis-and-research-traceability
description: "A user has a defined corpus or retrieval record and needs comparison, synthesis, conflict handling or research traceability. Exclude: unlogged corpus expansion; majority vote over conflicting evidence; clinical advice without governed specialist review."
---

# Evidence Synthesis and Research Traceability

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce a transparent evidence synthesis in which every material claim maps to appropriate sources and dissent remains visible. Exclusions are declared in the trigger above.

## Inputs

- bounded evidence corpus
- claim or review questions
- inclusion criteria and evidence hierarchy
- citation and traceability requirements

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **evidence-hierarchy.** Which evidence hierarchy should govern conflicts in this corpus? Recommended: Define the hierarchy before synthesis and keep community signals separate from scientific evidence.
2. **claim-criteria.** Which criteria determine whether a source supports a material claim? Recommended: Predeclare claim inclusion, contradiction and uncertainty criteria before mapping sources.

## Workflow

1. Freeze the corpus and synthesis questions.
2. Extract claims, methods, populations and limitations without losing source identity.
3. Map support and conflict under an explicit evidence hierarchy.
4. Report qualified conclusions, dissent, missing evidence and traceability links.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- claim-to-source graph or table
- evidence-quality and conflict summary
- qualified conclusions, gaps and excluded evidence

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Accept only a frozen corpus with a retrieval record and stable identifiers; if absent, return a retrieval handoff and do not search silently
- Map each material claim to sources at appropriate granularity and preserve support, conflict, uncertainty, and missing evidence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
