---
name: bioinformatics-format-and-identifier-validation
description: "Structurally validate declared FASTA/FASTQ/GenBank, SAM/BAM/CRAM, VCF/BCF, NCBI accession.version, or UniProt public identifier syntax, with an optional exact-accession existence check. Exclude record retrieval, cross-namespace mapping, conversion, repair, interpretation, and dedicated object formats."
license: Apache-2.0
metadata:
  version: "0.9.0"
---

# Bioinformatics Format and Identifier Validation

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Return non-mutating structural findings for the declared supported formats and
identifier namespaces, plus an optional exact-accession existence check.

## Inputs

- file paths or bounded text samples
- claimed formats and compression
- identifier namespace, organism or reference build when relevant

## Intake

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

## Public network execution

An explicit exact-accession existence check authorizes a bounded anonymous
lookup with `ncbi-eutils` or `uniprot-rest`; send identifiers, not local file
contents. Route record fields, searches, and cross-namespace mappings to
`biological-database-record-retrieval-and-identifier-resolution`.
Confirm only sensitive data, non-default hosts, or unrequested bulk. On failure,
return `needs-tool` or a non-completed partial result. Record provider, access
time, response status, returned identifiers, and network use.

## Workflow

1. Inventory inputs and inspect only bounded content.
2. Validate container, syntax and format-specific invariants.
3. Validate namespace and version syntax; when requested, check exact-accession existence through the bounded public lookup without retrieving unrelated records.
4. Report exact failures, uncertainty and a non-destructive next step.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- per-input pass, warning and failure findings
- detected versus claimed format and namespace
- bounded repair plan without silent mutation

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). A lookup proves only
the checked provider response, not semantic correctness or scientific validity.

## Guardrails

- Declare the exact format or namespace before validation
- Distinguish structural validity from semantic correctness and database existence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
