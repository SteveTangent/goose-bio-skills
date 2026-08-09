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
- `OpenAlex`
- `BioStudies`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| NCBI E-utilities | rolling API; 3 requests/s without key and 10 requests/s default with key | [PubMed, GEO/GDS, and SRA metadata search](https://www.ncbi.nlm.nih.gov/books/NBK25497/) | 2026-08-08 |
| Europe PMC | API 6.9 | [REST search API](https://europepmc.org/RestfulWebService) | 2026-08-08 |
| OpenAlex | rolling API; key required for production since 2026-02-13 | [metered production API](https://developers.openalex.org/guides/authentication) | 2026-08-08 |
| BioStudies | v1; pageSize maximum 100 | [REST /api/v1/search](https://www.ebi.ac.uk/biostudies/help%23API) | 2026-08-08 |

## Network and data boundary

Live retrieval necessarily sends query terms, dates, identifiers, and possibly an API key. OpenAlex production use is metered and must not cross a free or paid quota without explicit authorization. No controlled or unpublished terms should be sent silently.

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

- Mode: `skipped-complex-tool`
- Reason: Live multi-provider retrieval, credentials, pagination, rate limiting, paid quota, bulk PDF and raw-study downloads were not run.
- Relevant versions: NCBI E-utilities rolling, Europe PMC API 6.9, OpenAlex metered API, BioStudies API v1
- Unverified boundaries:
  - Live search completeness, provider drift, pagination, rate limiting, authentication, and paid quota behavior have not been evaluated
  - Bulk full-text, PDF, GEO raw file, SRA read, Aspera, cloud, and very large corpus downloads are outside this preview

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
