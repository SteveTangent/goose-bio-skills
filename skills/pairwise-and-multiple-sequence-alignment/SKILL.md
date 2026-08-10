---
name: pairwise-and-multiple-sequence-alignment
description: "A user needs global, local or multiple alignment of an existing sequence set. Exclude: database similarity search; tree inference; asserting positional homology without qualification."
license: Apache-2.0
metadata:
  version: "0.6.0"
---

# Pairwise and Multiple Sequence Alignment

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce an alignment fit for a declared downstream purpose and report sensitivity to key alignment choices. Exclusions are declared in the trigger above.

## Inputs

- validated sequence records
- alignment objective
- sequence type and expected divergence
- for hosted upload: data class, provider, service, and one-job scope

## Intake

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait; otherwise continue authorized work. Patient, PHI, and
controlled-access data are a terminal hosted-upload block.

Decision order:

1. **remote-data-authorization.** May the disclosed sequences be uploaded to the named EMBL-EBI service for this one job? Recommended: prefer local; authorize only the disclosed non-controlled scope.
2. **alignment-objective.** Which downstream question must the alignment support? Recommended: choose local, global, or multiple alignment from that question.

## Public network execution

Prefer local alignment. An exact current request authorizes one disclosed,
non-sensitive job without repeat confirmation; other allowed sensitive data
requires one scoped confirmation. Never upload patient, PHI, controlled data,
credentials, or secrets. Without a reviewed adapter return `needs-tool`.
Record input digest, parameters, job ID, status, result hash, and network use.

## Workflow

1. Check type, count, length, divergence, and upload sensitivity without copying raw data into provenance.
2. Select global, local or multiple alignment based on the stated objective.
3. Choose local execution or resolve exact hosted-job authorization.
4. Run locally or use the explicitly authorized adapter with stable input order.
5. Report coverage, gaps, unstable regions and downstream-use limitations.
6. Without a compatible adapter, return `needs-tool` or `dry-run`.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- alignment artifact
- method, version and parameter record
- alignment statistics and low-confidence regions

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Remote completion
does not establish positional homology or cross-engine equivalence.

## Guardrails

- Separate pairwise from multiple alignment and declare nucleotide or protein input
- Record objective, scoring, gaps, strategy, threads, seed, and input order
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Never mark partial or skipped execution `completed`
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
