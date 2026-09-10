---
name: bulk-rnaseq-gene-count-matrix-assembly
description: "Assemble a gene-count matrix from completed compatible single-sample counting reports with the same annotation and assignment policy. Exclude read counting, normalization and differential expression."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Bulk RNA-seq Gene-count Matrix Assembly

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use to assemble at least two completed schema-1.0 single-sample gene-count JSON reports from bulk-rnaseq-gene-counting-from-alignment into one deterministic gene-by-sample raw-count JSON matrix. Require exact agreement on the GTF SHA-256, every gene's gene_id/contig/strand/exon_count tuple, and the full assignment contract; sort samples and genes and fail closed on duplicate keys, duplicate samples, mismatches, or invalid counts. Exclude SAM/BAM/CRAM counting, annotation repair or gene completion, filtering, normalization, transformation, batch correction, differential expression, and biological or clinical interpretation.

## Owns

Join already-completed, single-sample raw gene-count reports into one exact
gene-by-sample matrix. Preserve the upstream count and assignment semantics;
make no scientific comparison or alteration.

## Inputs and intake

Require at least two local JSON files produced by
`bulk-rnaseq-gene-counting-from-alignment` schema `1.0`, plus one new JSON
output path. Each source must have `status: completed` and a unique sample ID.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **count-set.** Which completed reports belong in this matrix? Recommended:
   use only samples counted against the same immutable GTF and fixed assignment
   policy for one intended cohort.
2. **upstream-validity.** Have the source reports and their upstream SAM/GTF
   contracts already been reviewed? Recommended: stop and review them first;
   this skill verifies report agreement, not the underlying biological inputs.

An explicit bounded local assembly request authorizes reading the named reports
and creating one new matrix when those facts are already supplied.

## Run

```text
python3 scripts/assemble_gene_count_matrix.py \
  --count-json SAMPLE_A.json SAMPLE_B.json [MORE.json ...] \
  --output NEW_MATRIX.json
```

Use Python 3.10+ standard library only. The helper rejects duplicate JSON keys,
invalid or oversized values, fewer than two or too many samples, different
GTF fingerprints, gene-row tuples, or assignment contracts, unsafe paths,
symlinks, and existing outputs. Read [the exact assembly contract](references/assembly-contract.md)
before interpreting the matrix.

## Output contract

Publish one deterministic JSON object containing:

- samples sorted by sample ID with source SHA-256 fingerprints;
- genes sorted by gene ID with contig, strand, exon count, and counts aligned
  to the sorted sample order;
- the common GTF SHA-256 and complete common assignment contract;
- fixed bounds and explicit limitations, without local input paths.

`completed` means the inputs agreed exactly on the bounded structural contract
and the create-new report was published. It does not mean the cohort, counts,
or annotation are scientifically valid or comparable.

## Guardrails

- Never count alignments, infer or repair genes, or merge non-identical gene
  definitions or assignment policies.
- Never fill missing genes, filter counts, normalize, transform, correct batch
  effects, test differential expression, or interpret biology.
- Never overwrite, mutate inputs, create directories except the explicit DE handoff bundle, follow symlinks, escape
  the working directory, use the network, or start a subprocess.
- Treat publication as create-new with tested rollback after staged identity is
  recorded, not as crash-atomic replacement. A rare pre-identity failure may
  leave a hidden mode-0600 stage; do not write into a concurrently hostile directory.
- Require researcher review of cohort membership, reference identity, upstream
  QC, library protocols, count policy, design suitability, and downstream use;
  no clinical authority.
