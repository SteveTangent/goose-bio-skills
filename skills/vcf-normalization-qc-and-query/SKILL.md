---
name: vcf-normalization-qc-and-query
description: "Check reference, allele or genotype semantics; normalize, filter or query existing VCF records. Exclude syntax-only validation, variant calling, pathogenicity reassessment and clinical decisions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# VCF Normalization, QC and Query

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


Detailed scope: A user needs VCF-specific reference, allele, genotype, normalization, filtering or query semantics on an existing callset. Exclude: syntax/schema-only validation without VCF-specific semantic QC or operation; variant calling; clinical classification; treating imputed dosage as a directly observed genotype.

## Owns

Produce an auditable normalized or filtered variant representation and QC findings from an existing callset. Apply the detailed scope below.

## Inputs

- VCF or BCF
- exact reference FASTA and build
- normalization and query policy

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **vcf-reference.** Which exact reference FASTA and build should govern this VCF operation? Recommended: Require a compatible immutable reference release or digest and stop on contig or REF incompatibility.
2. **multiallelic-decomposition.** Should multiallelic records be decomposed? Recommended: Decompose only when the downstream contract requires it and preserve a mapping to original records.
3. **vcf-traceability.** Which original VCF fields must remain traceable after transformation? Recommended: Retain identifiers, alleles, genotype semantics and declared annotations in an explicit transformation log.

## Workflow

1. Verify header, contigs, samples and exact reference identity.
2. Check REF alleles and representation before transformation.
3. Apply declared decomposition, left-alignment, filtering or query operations.
4. Compare counts and genotype semantics before and after.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- normalized or queried artifact
- REF, header, sample and genotype checks
- record transformation and rejection log

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Require the exact reference FASTA, assembly, contig convention, and digest before normalization
- Declare multiallelic decomposition, left-alignment, filtering, and missing-value policies
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
