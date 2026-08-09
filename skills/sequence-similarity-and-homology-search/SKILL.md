---
name: sequence-similarity-and-homology-search
description: "A user needs candidate homologs or similar sequences from a fixed, question-appropriate complete or curated database, or a disclosed remote adapter. Exclude: building or downloading a complete reference database; multiple sequence alignment; claiming function from percent identity alone."
license: Apache-2.0
metadata:
  version: "0.2.1"
---

# Sequence Similarity and Homology Search

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Run or plan a reproducible query-to-database similarity search and qualify what the hits do and do not support. Exclusions are declared in the trigger above.

## Inputs

- validated query sequences
- question-appropriate complete or curated target database with release and digest
- search sensitivity and resource constraints

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **database-mode.** Which fixed complete or curated database is appropriate for this research question? Recommended: Use a question-appropriate database fixed by release and digest; reserve a micro database for installation smoke only.

## Workflow

1. Validate query alphabet and target database identity.
2. Choose a search strategy from sequence type and sensitivity needs.
3. Run a pinned local search or disclose an optional network adapter.
4. Filter and report hits using coverage and statistical evidence, not identity alone.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- ranked hit table with identity, query and target coverage and statistics
- database, version and parameter record
- homology and annotation caveats

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Record query molecule type, engine and version, database release or digest, masking, E-value, coverage, hit cap, and all non-default parameters
- Use a micro database only for installation smoke, never for research interpretation
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
