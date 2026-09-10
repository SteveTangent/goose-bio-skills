# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`bioinformatics-format-and-identifier-validation`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare the exact format or namespace before validation
- Distinguish structural validity from semantic correctness and database existence
- Use accession.version when a specific sequence version matters
- Do not present a regular-expression match as proof that an accession exists
- Route record retrieval and cross-namespace mapping to the biological-database record Skill

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
| UniProt REST | rolling API; access-date bound | [exact public accession lookup](https://www.uniprot.org/help/programmatic_access) | 2026-08-09 |

## Network and data boundary

Local syntax and structure checks are offline. An optional existence check uses
NCBI E-utilities for one exact NCBI accession.version or UniProt REST for one
exact public accession. Record retrieval, search, cross-namespace mapping, and
asynchronous UniProt ID-mapping belong elsewhere. Record the authority,
identifier version, and lookup time.

The user's explicit validation request authorizes the targeted public read and
bounded response above. Anonymous access requires no provider configuration or
optional API key. Confirm only an unrequested bulk expansion, sensitive upload,
remote job, credential-required path, paid use, or non-default host.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Network transport follows the agent host's proxy and CA trust policy; the
shared companion does not read provider configuration or credentials.

Use the declared default public provider directly for the requested bounded
read or download. If a confirmation condition applies, disclose the exact
provider, data, scope, destination, credential and billing boundary first; do
not reconfirm an exact action already authorized by the current request, except
for sensitive data. On missing adapters, unavailable network, provider failure,
truncation, or missing authorization, degrade honestly and never claim a call.

## Verification status

- Mode: `not-performed`
- Reason: The preview defines bounded local structural checks outside the new sample-table adapter; live NCBI and UniProt resolution was not run.
- Relevant versions: Biopython 1.87, hts-specs rolling documentation checked 2026-08-08, NCBI sequence identifier documentation checked 2026-08-08, UniProt REST documentation checked 2026-08-09
- Unverified boundaries:
  - Large-directory and compressed-file batch validation has not been run
  - Live NCBI and UniProt accession existence and metadata lookup behavior has not been runtime-evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.


## New sample-table helper

# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: Sample TSV; optional matrix; declared sample/group/subject/batch columns, matrix scale and explicit renames.

Outputs: New samples.tsv and validation.json with input hashes, renames, sample order, unresolved fields and design warnings.

Unsupported: Inferred groups, silent sample drops, automatic ID mapping, data imputation or choosing a statistical model.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
