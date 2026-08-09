---
name: sequence-similarity-and-homology-search
description: "A user needs candidate homologs or similar sequences from a fixed suitable local database or a disclosed remote adapter. Exclude: building a reference database; multiple alignment; claiming function from identity alone."
license: Apache-2.0
metadata:
  version: "0.4.1"
---

# Sequence Similarity and Homology Search

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Run or plan a reproducible similarity search and qualify what its hits support.

## Inputs

- validated query sequences
- local: suitable database release and digest; remote: reviewed provider and database name
- sensitivity and resource limits
- for remote upload: data class, provider, database, and one-job scope

## Intake

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait; otherwise continue authorized work. Patient, PHI, and
controlled-access data are a terminal remote-upload block.

Decision order:

1. **remote-data-authorization.** May the disclosed query be uploaded to NCBI Remote BLAST against the named database for this one job? Recommended: prefer local; authorize only the disclosed non-controlled scope.
2. **database-mode.** Which target database should this search use? Recommended: fix local data by release/digest; name the remote database.

## Public network execution

Prefer a pinned local database. An exact current request authorizes one
disclosed, non-sensitive job without repeat confirmation; other allowed
sensitive data requires one scoped confirmation. Never upload patient, PHI,
controlled data, credentials, or secrets. Without a reviewed adapter return
`needs-tool`. Record query digest, database, parameters, RID, status, result
hash, and network use.

## Workflow

1. Validate the query and classify upload sensitivity without copying raw data into provenance.
2. Fix local database release/digest; for remote work record its name, available version, and access time.
3. Choose local execution or resolve exact remote authorization.
4. Run locally or use the authorized adapter; otherwise return `needs-tool` or `dry-run`.
5. Filter and report hits using coverage and statistical evidence, not identity alone.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- ranked hits with identity, coverage, and statistics
- database/version and parameters
- homology caveats

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Remote completion
does not prove function or database completeness.

## Guardrails

- Record molecule type, engine/version, database, masking, E-value, coverage, hit cap, and non-defaults
- Use a micro database only for installation smoke, never for research interpretation
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Never mark partial or skipped execution `completed`
- Require researcher review for biological interpretation; no clinical authority
