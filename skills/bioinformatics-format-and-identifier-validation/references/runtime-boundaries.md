# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`bioinformatics-format-and-identifier-validation`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare the exact format or namespace before validation
- Distinguish structural validity from semantic correctness and database existence
- Use accession.version when a specific sequence version matters
- Do not present a regular-expression match as authoritative identifier resolution

## Optional adapters

- `Biopython Bio.SeqIO`
- `GA4GH/hts-specs`
- `NCBI sequence identifiers`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Biopython Bio.SeqIO | Biopython 1.87 | [bounded parsing of declared FASTA, FASTQ, and GenBank sequence formats](https://biopython.org/docs/1.87/api/Bio.SeqIO.html) | 2026-08-08 |
| GA4GH/hts-specs | rolling specifications; no unified release tag | [SAM/BAM/CRAM and VCF/BCF specifications](https://github.com/samtools/hts-specs) | 2026-08-08 |
| NCBI sequence identifiers | rolling namespace documentation | [accession.version identifier semantics](https://www.ncbi.nlm.nih.gov/genbank/sequenceids/) | 2026-08-08 |

## Network and data boundary

Local syntax and structure checks are offline. Live identifier resolution is an explicit optional network action; record the authority, accession version, and resolution time.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

### External service gate

- `disclosure`: `provider-purpose-would_send-credential-billing`
- `confirmation`: `two-stage-exact-token`
- `config_access`: `after-exact-token-only`
- `companion_mode`: `zero-network-plan-only`
- `standalone_fallback`: `needs-user-config-or-needs-tool`
- `call_claim`: `forbidden-before-live-execution`

Before any external-service call, disclose the catalog provider ID, purpose,
`would_send` fields, credential requirements, and billing or quota terms. With
the repository companion, stage 1 runs root `scripts/check_research_connectors.py`
with provider IDs only and no config path; it emits a `confirmation_token`
without touching user config. Stage 2 may read config and produce a zero-network
plan only after the user returns that exact token; neither stage calls a provider.
For a standalone install or missing user configuration, fail closed with
`needs-user-config` or `needs-tool`; never claim that the service was called.

## Verification status

- Mode: `not-performed`
- Reason: The preview defines bounded local structural checks but ships no validator implementation; cross-database resolution was not run.
- Relevant versions: Biopython 1.87, hts-specs rolling documentation checked 2026-08-08, NCBI sequence identifier documentation checked 2026-08-08
- Unverified boundaries:
  - Large-directory and compressed-file batch validation has not been run
  - Online identifier existence across NCBI, ENA, UniProt, and other authorities has not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
