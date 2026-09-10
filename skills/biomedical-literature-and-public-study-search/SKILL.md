---
name: biomedical-literature-and-public-study-search
description: "Find biomedical publications and public study accessions from a research question. Exclude evidence synthesis, read downloads and clinical recommendations."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Biomedical Literature and Public Study Search

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


Detailed scope: A user needs publications, public-study metadata, or study-accession discovery for a biomedical question. Exclude claim synthesis, community-only search, clinical recommendations, and non-study identifier resolution.

## Owns

Retrieve and screen a traceable corpus of publications or public studies while separating discovery signals from scientific evidence. Apply the detailed scope below.

## Inputs

- research question and concepts
- target literature or study databases
- date, organism, assay and study constraints
- inclusion and exclusion criteria

## Intake

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

Decision order:

1. **retrieval-objective.** Should this search prioritize recall for screening or precision for a bounded quick answer? Recommended: Start with reproducible recall, then apply explicit screening criteria.

## Public network execution

An explicit search authorizes bounded anonymous reads from `ncbi-eutils`,
`europe-pmc`, and `ebi-biostudies`, including requested public metadata and
open-access files. Paid providers are not fallbacks. Confirm only sensitive
material, non-default hosts, or unrequested bulk. On failure, return
`needs-tool` or partial, never `completed`. Record query, provider, pages,
identifiers, access time, hashes, and network use.

## Workflow

1. Translate the question into concepts, synonyms and database-specific queries.
2. Choose broad recall or narrow precision deliberately.
3. Retrieve through recorded responses or the bounded public adapters above.
4. Deduplicate, screen and report query, date, identifiers and missing coverage.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- exact search queries and access dates
- deduplicated result set with stable identifiers
- screening decisions and unresolved retrieval gaps

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Live retrieval does
not prove corpus completeness; `completed` requires all declared pages.

## Guardrails

- Record each exact query, provider, date, pagination range, returned stable identifiers, response fingerprint, and screening criteria
- Deduplicate by stable identifiers while retaining versions, retractions, corrections, and conflicting records
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
