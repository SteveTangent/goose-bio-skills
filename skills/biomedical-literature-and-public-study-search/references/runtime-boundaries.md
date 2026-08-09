# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`biomedical-literature-and-public-study-search`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record each exact query, provider, date, pagination range, returned stable identifiers, response fingerprint, and screening criteria
- Deduplicate by stable identifiers while retaining versions, retractions, corrections, and conflicting records
- Treat discovery ranking as a search aid rather than evidence quality
- Limit accession handling to publications and public studies; route gene, protein, variant, molecule, and structure identifiers elsewhere
- Default to metadata discovery and screening; raw studies and full text require a separate bounded retrieval plan

## Optional adapters

- `NCBI E-utilities`
- `Europe PMC`
- `BioStudies`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| NCBI E-utilities | rolling API; 3 requests/s without key and 10 requests/s default with key | [PubMed, GEO/GDS, and SRA metadata search](https://www.ncbi.nlm.nih.gov/books/NBK25497/) | 2026-08-08 |
| Europe PMC | API 6.9 | [REST search API](https://europepmc.org/RestfulWebService) | 2026-08-08 |
| BioStudies | v1; pageSize maximum 100 | [REST /api/v1/search](https://www.ebi.ac.uk/biostudies/help%23API) | 2026-08-08 |

## Network and data boundary

Live retrieval sends query terms, dates, and identifiers to the selected public
provider. Metered or paid literature providers are outside this contract and
must not be used as a fallback. No controlled or unpublished terms should be
sent silently.

The user's explicit search request authorizes the targeted public reads and
bounded downloads above. Anonymous access requires no provider configuration or
optional API key. Confirm only an unrequested bulk expansion, sensitive upload,
remote job, credential-required path, or non-default host.

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

- Mode: `skipped-complex-tool`
- Reason: Live public-provider retrieval, pagination, rate limiting, authentication, bulk PDF, and raw-study downloads were not run.
- Relevant versions: NCBI E-utilities rolling, Europe PMC API 6.9, BioStudies API v1
- Unverified boundaries:
  - Live search completeness, provider drift, pagination, rate limiting, and authentication behavior have not been evaluated
  - Bulk full-text, PDF, GEO raw file, SRA read, Aspera, cloud, and very large corpus downloads are outside this preview

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
