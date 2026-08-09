---
name: bioinformatics-format-and-identifier-validation
description: "A user requests bounded structural validation of declared FASTA, FASTQ, GenBank, SAM/BAM/CRAM, VCF/BCF, or NCBI accession.version input. Exclude: sequence transformation or format conversion; VCF allele normalization, filtering, query, genotype semantics or VCF-specific QC; whole-dataset scientific analysis or biological interpretation; unrequested file rewriting; pure memory or capacity preflight without a bioinformatics format or identifier contract; single-cell object, molecule, or protein-structure validation owned by a dedicated Skill."
---

# Bioinformatics Format and Identifier Validation

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Return non-mutating structural findings for declared sequence, HTS, variant, or NCBI accession.version inputs supported by the reviewed interfaces. Exclusions are declared in the trigger above.

## Inputs

- file paths or bounded text samples
- claimed formats and compression
- identifier namespace, organism or reference build when relevant

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **invalid-record-handling.** Should invalid records remain report-only or be written to a separate repaired artifact? Recommended: Report first; create a separate repaired artifact only after confirmation.

## Workflow

1. Inventory inputs and inspect only bounded content.
2. Validate container, syntax and format-specific invariants.
3. Resolve identifier namespace and reference context without guessing.
4. Report exact failures, uncertainty and a non-destructive next step.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- per-input pass, warning and failure findings
- detected versus claimed format and namespace
- bounded repair plan without silent mutation

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Declare the exact format or namespace before validation
- Distinguish structural validity from semantic correctness and database existence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
