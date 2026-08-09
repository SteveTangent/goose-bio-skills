---
name: biomedical-literature-and-public-study-search
description: "A user needs publication or public-study literature, metadata, or accession discovery for a defined biomedical question. Exclude: claim-level evidence synthesis; treating community posts as validation; clinical recommendation; community-discussion or complaint-only search; non-publication and non-study accession resolution."
license: Apache-2.0
metadata:
  version: "0.2.1"
---

# Biomedical Literature and Public Study Search

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Retrieve and screen a traceable corpus of publications or public studies while separating discovery signals from scientific evidence. Exclusions are declared in the trigger above.

## Inputs

- research question and concepts
- target literature or study databases
- date, organism, assay and study constraints
- inclusion and exclusion criteria

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **retrieval-objective.** Should this search prioritize recall for screening or precision for a bounded quick answer? Recommended: Start with reproducible recall, then apply explicit screening criteria.

## Workflow

1. Translate the question into concepts, synonyms and database-specific queries.
2. Choose broad recall or narrow precision deliberately.
3. Retrieve through recorded responses or disclosed read-only adapters.
4. Deduplicate, screen and report query, date, identifiers and missing coverage.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- exact search queries and access dates
- deduplicated result set with stable identifiers
- screening decisions and unresolved retrieval gaps

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Record each exact query, provider, date, pagination range, returned stable identifiers, response fingerprint, and screening criteria
- Deduplicate by stable identifiers while retaining versions, retractions, corrections, and conflicting records
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
