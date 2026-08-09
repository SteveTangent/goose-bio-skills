# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`alignment-file-operations`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Bind every operation to the exact reference assembly, sequence dictionary, and reference digest
- Declare sort order, index state, region coordinate semantics, MAPQ, secondary, supplementary, and duplicate policies
- For CRAM, make reference retrieval explicit and record REF_PATH or REF_CACHE behavior
- Route read QC, trimming, alignment generation, and variant calling elsewhere

## Optional adapters

- `samtools`
- `HTSlib`
- `pysam`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| samtools | 1.24 | [SAM/BAM/CRAM command-line inspection, transformation, and indexing](https://github.com/samtools/samtools/releases/) | 2026-08-08 |
| HTSlib | 1.24 native stack; distinct from pysam's bundled stack | [SAM/BAM/CRAM and VCF/BCF library stack used by native tools](https://github.com/samtools/htslib/releases/) | 2026-08-08 |
| pysam | 0.24.0; bundles htslib/samtools/bcftools 1.23.1, not native 1.24 | [Python SAM/BAM/CRAM bindings](https://github.com/pysam-developers/pysam/releases) | 2026-08-08 |

## Network and data boundary

Local SAM/BAM operations are offline. CRAM reference URLs, refget, S3, or HTTP input require network and possibly credentials; disclose the exact reference identity and destination.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Multi-gigabyte sorting, indexing, merging, remote object storage, reference-cache construction, and CRAM batch round trips were not run.
- Relevant versions: native samtools/HTSlib 1.24, pysam 0.24.0 with a separate bundled 1.23.1 stack
- Unverified boundaries:
  - Large BAM/CRAM sort, index, merge, and round-trip behavior has not been evaluated
  - Remote HTTP/S3 input, refget, and reference-cache behavior has not been tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
