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
- `UniProt REST`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Biopython Bio.SeqIO | Biopython 1.87 | [bounded parsing of declared FASTA, FASTQ, and GenBank sequence formats](https://biopython.org/docs/1.87/api/Bio.SeqIO.html) | 2026-08-08 |
| GA4GH/hts-specs | rolling specifications; no unified release tag | [SAM/BAM/CRAM and VCF/BCF specifications](https://github.com/samtools/hts-specs) | 2026-08-08 |
| NCBI sequence identifiers | rolling namespace documentation | [accession.version identifier semantics](https://www.ncbi.nlm.nih.gov/genbank/sequenceids/) | 2026-08-08 |
| UniProt REST | rolling API; access-date bound | [entry retrieval and search](https://www.uniprot.org/help/programmatic_access) | 2026-08-09 |

## Network and data boundary

Local syntax and structure checks are offline. Live identifier resolution uses
NCBI E-utilities for NCBI accession.version records and UniProt REST for public
entry retrieval or search. Asynchronous UniProt ID-mapping submission is outside
this read-only adapter. Record the authority, identifier version, and resolution
time.

The user's explicit validation request authorizes the targeted public read and
bounded response above. Anonymous access requires no provider configuration or
optional API key. Confirm only an unrequested bulk expansion, sensitive upload,
remote job, credential-required path, paid use, or non-default host.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-user-config`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Use the declared default public provider directly for the requested bounded
read or download. If a confirmation condition applies, disclose the exact
provider, data, scope, destination, credential and billing boundary first; do
not reconfirm an exact action already authorized by the current request, except
for sensitive data. On missing adapters, unavailable network, provider failure,
truncation, or missing authorization, degrade honestly and never claim a call.

## Verification status

- Mode: `not-performed`
- Reason: The preview defines bounded local structural checks but ships no validator implementation; live NCBI and UniProt resolution was not run.
- Relevant versions: Biopython 1.87, hts-specs rolling documentation checked 2026-08-08, NCBI sequence identifier documentation checked 2026-08-08, UniProt REST documentation checked 2026-08-09
- Unverified boundaries:
  - Large-directory and compressed-file batch validation has not been run
  - Live NCBI and UniProt accession existence and metadata lookup behavior has not been runtime-evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
