# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`vcf-normalization-qc-and-query`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Require the exact reference FASTA, assembly, contig convention, and digest before normalization
- Declare multiallelic decomposition, left-alignment, filtering, and missing-value policies
- Preserve original allele, genotype, INFO, FORMAT, and annotation semantics with before-and-after counts
- Route phasing and imputation to separate reviewed workflows

## Optional adapters

- `bcftools`
- `HTSlib`
- `TileDB-VCF`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| bcftools | 1.24 | [VCF/BCF normalization, query, and filtering](https://github.com/samtools/bcftools/releases) | 2026-08-08 |
| HTSlib | 1.24 | [VCF/BCF I/O and indexing library](https://github.com/samtools/htslib/releases/) | 2026-08-08 |
| TileDB-VCF | 0.40.3 | [large cohort VCF storage and query](https://github.com/TileDB-Inc/TileDB-VCF/releases) | 2026-08-08 |

## Network and data boundary

Local VCF/BCF and reference files can be processed offline. HTTP, S3, and TileDB Cloud are optional network paths and must disclose locations, credentials, and data sent.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Reference-bound normalization, large cohorts, cloud storage, and TileDB dataset execution were not staged for this preview.
- Relevant versions: bcftools 1.24, HTSlib 1.24, TileDB-VCF 0.40.3 optional, reference FASTA not-staged
- Unverified boundaries:
  - Actual normalization against a hash-bound reference FASTA has not been run
  - Large cohorts, HTTP/S3, TileDB Cloud, and TileDB schema migration behavior have not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
