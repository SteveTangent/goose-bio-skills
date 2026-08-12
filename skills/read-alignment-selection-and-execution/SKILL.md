---
name: read-alignment-selection-and-execution
description: "Use to align one tiny local plain-FASTQ file of single-end short genomic DNA reads to one exact local plain-FASTA reference with an explicitly supplied, digest-pinned minimap2 2.31-r1302 executable, producing a create-new SAM and provenance report. Exclude QC, trimming, paired-end or interleaved reads, RNA/splice or long-read alignment, reference choice, sorting, indexing, BAM/CRAM operations, variant calling, quantification, batches, and overwrites."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Read Alignment Selection and Execution

`Preview + reviewed`; the bounded fake-adapter self-test passed. Real minimap2
execution, agent runtime, scientific benchmarking, representative-data testing,
and expert review were not performed.

## Owns

Run one fixed `minimap2 -a -x sr` branch for a tiny, single-end short genomic
DNA FASTQ against the exact supplied FASTA. This preview does not select a
reference or another alignment strategy.

## Inputs and intake

Require one plain local FASTA, one plain local FASTQ, a new SAM leaf name, a new
JSON-report leaf name, and an absolute non-symlink minimap2 executable plus its
expected SHA-256. All data paths must remain under the current working directory
without symlink components.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **reference-contract.** Which exact local FASTA is the intended reference? Recommended: use the producer-approved reference file and bind the run to its SHA-256; never infer or substitute a build.
2. **assay-contract.** Are these plain single-end short genomic DNA reads? Recommended: continue only with an explicit declaration; route paired/interleaved, RNA/splice, or long reads elsewhere.

An explicit local alignment request authorizes bounded reads, one fixed local
subprocess, private temporary work, and the two requested create-new outputs.

## Run

```text
python3 scripts/run_short_dna_alignment.py \
  --reference reference.fa --reads reads.fastq \
  --minimap2 /absolute/path/to/minimap2 \
  --minimap2-sha256 EXPECTED_64_HEX_DIGEST \
  --output-sam aligned.sam --output-report aligned.provenance.json \
  --declared-single-end-short-genomic-dna
```

Install minimap2 separately; this package never downloads or installs it. The
Python 3.10+ executor accepts one bounded uncompressed FASTA and FASTQ, copies
their validated bytes into private work, and invokes only minimap2 2.31-r1302
with fixed arguments, one thread, a fixed seed, no shell, and a clean
environment. The caller-supplied executable digest is an operator approval
boundary and must come from an independently reviewed source. Missing or
incompatible tools fail closed. Processing order is declaration, executable
binding, then input validation and execution.

## Output contract

`completed` creates a SAM plus deterministic JSON containing input and executable
fingerprints, reference/read dimensions, the fixed command template, minimap2
version, mapped and unmapped primary-read counts, SAM dimensions and hash, and
output names. Existing or unsafe targets are never replaced.

A missing assay declaration returns `needs-decision`. Invalid caller inputs or
paths return `invalid-input`. A missing, changed, digest-mismatched,
wrong-version, timed-out, or failed adapter—and malformed or irreconcilable SAM
returned by that adapter—returns `needs-tool`. No output is called completed
unless the SAM reference dictionary matches the FASTA, every input read has
exactly one coherent primary record, and both new artifacts are published.

## Guardrails

- Never install, download, use the network, mutate inputs, follow symlinks, escape the current directory, overwrite, invoke a shell, or accept caller flags.
- Never infer a reference, assay, pairing state, orientation, or biological quality from alignment counts.
- Exclude QC/trimming, paired-end/interleaved input, RNA/splice and long reads, multi-reference selection, sorting/indexing, BAM/CRAM operations, variant calling, quantification, and batches.
- Treat mapped fraction as descriptive execution evidence, not assay validity, absence of contamination, or clinical evidence.
- Require researcher review of reference provenance, library type, alignment suitability, and downstream interpretation; no clinical or diagnostic authority.
