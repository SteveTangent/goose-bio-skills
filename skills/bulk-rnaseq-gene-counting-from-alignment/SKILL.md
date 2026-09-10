---
name: bulk-rnaseq-gene-counting-from-alignment
description: "Count primary single-end SAM alignments against a GTF with explicit strand and MAPQ policies. Exclude paired-end counting, transcript quantification and differential expression."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Bulk RNA-seq Gene Counting from Alignment

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


Detailed scope: Use to assign one bounded local primary single-end bulk RNA-seq SAM sample to gene_id exon unions in one exact local GTF, with explicit unstranded, forward, or reverse library semantics and a declared MAPQ floor. Produce a create-new JSON gene-count table plus assignment categories and provenance. Exclude raw-read alignment, paired-end fragment counting, transcript or isoform abundance, probabilistic multimapper allocation, normalization, differential expression, batches, and biological interpretation.

## Owns

Count one small primary single-end SAM sample against `gene_id` exon unions in
one exact GTF without modifying either input. Keep ambiguous, no-feature,
wrong-strand, low-MAPQ, multimapped, QC-failed, and unmapped assignments
separate from gene counts.

## Inputs and intake

Require a plain local SAM, a matching plain local GTF, a sample ID, a new JSON
output path, one declared strandedness value, and a MAPQ floor from 0 through
255. Inspect safe facts first. Ask one unresolved decision with a recommendation,
then wait:

1. **annotation-reference.** Which exact GTF belongs to the SAM reference dictionary? Recommended: use the annotation built for the same immutable reference release and stop on unknown contigs.
2. **library-strandedness.** Is the library unstranded, forward, or reverse? Recommended: use the library-preparation record; never infer strandedness from the alignments in this preview.
3. **minimum-mapq.** Which aligner-appropriate MAPQ floor was prespecified? Recommended: use the project policy recorded before counting and preserve the value in the output.

An explicit bounded local counting request authorizes the input reads and one
create-new report.

## Run

```text
python3 scripts/count_gene_alignments.py \
  --sam SAMPLE.sam --gtf GENES.gtf --sample-id SAMPLE_ID \
  --strandedness unstranded|forward|reverse --min-mapq 20 \
  --output NEW_COUNTS.json
```

Use Python 3.10+ standard library only. The helper accepts one bounded,
uncompressed SAM with `@SQ` records and one bounded GTF whose exon rows each
have exactly one `gene_id`. If `@RG` headers declare `SM`, they must identify
one sample and match `--sample-id`. Read the exact details in
[counting-contract.md](references/counting-contract.md) before interpreting
strand or assignment categories. This positional assignment helper does not
validate SAM sequence/quality consistency or unmapped-record mate fields; use
the broader alignment-file validation workflow before counting when those
contracts are not already established.

## Output contract

Publish one deterministic JSON object containing:

- sample ID, input SHA-256 digests, adapter version, and declared policy;
- one sorted row per GTF gene with count, contig, strand, and exon-row count;
- reconciled primary-record categories and ignored secondary/supplementary counts;
- explicit duplicate and missing-`NH` observations plus limitations.

`completed` means the report was created and every primary record reconciled to
exactly one assignment category. Missing `NH` is accepted by the declared MAPQ
policy and reported; `NH>1` is unassigned rather than allocated fractionally.

## Guardrails

- Require single-end semantics; route paired-end fragment counting or broad batches to a separate tool-backed workflow.
- Bind GTF coordinates to SAM `@SQ`; never infer a reference or repair an annotation.
- Refuse multiple distinct `@RG` sample names and silent renaming of a sole declared `SM` value.
- Do not exclude a primary record solely for its duplicate flag; report duplicate-flag observations, and ignore/report secondary and supplementary records.
- Never align reads, estimate strandedness, allocate multimappers probabilistically, normalize counts, fit differential models, or infer transcript abundance.
- Never follow input/output symlinks, escape the current working directory, create directories, overwrite a path, use the network, or start a subprocess.
- Require researcher review of reference identity, library protocol, MAPQ semantics, and the assignment summary; no clinical authority.
