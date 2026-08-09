# Runtime and scientific boundaries

This reference defines the operating boundary for
`biological-database-record-retrieval-and-identifier-resolution` version
`0.4.1`. Interfaces were reviewed on 2026-08-09; this preview does not claim that
the exact Skill was runtime-evaluated.

## Scientific contract

- Select the provider from the declared identifier authority or requested database, not from search popularity.
- Preserve accession versions, all returned cross-references, one-to-many mappings, deprecated or replaced status, and not-found results.
- Treat a provider cross-reference as that provider's assertion, not proof of biological equivalence.
- Require an organism or taxon before resolving an ambiguous symbol.
- Keep local syntax validation, literature discovery, homology, structures, chemistry, and clinical interpretation outside this Skill.

## Shared live read-only adapter

The Skill uses the repository's shared connector for bounded anonymous `GET` or
`HEAD` requests to allowlisted public paths. It does not read provider keys,
contact identities, or paid tokens and does not accept arbitrary URLs.

Initial operations are intentionally narrow:

- `uniprot-rest`: bounded UniProtKB entry retrieval and synchronous search; no asynchronous ID-mapping submission.
- `ensembl-rest`: bounded stable-ID lookup, archive status, sequence, and cross-reference retrieval; no POST lookup batches.
- `ncbi-eutils`: EInfo, ESearch, ESummary, and bounded EFetch; no EPost or history-server state.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| UniProt REST | rolling API; database release `2026_02` | [API query guidance](https://www.uniprot.org/help/api_queries) and [2026_02 release](https://www.uniprot.org/help/2026-06-10-release) | 2026-08-09 |
| Ensembl REST | API `15.12` (July 2026) | [REST API information](https://rest.ensembl.org/documentation/info/rest) | 2026-08-09 |
| NCBI E-utilities | rolling API; anonymous public rate boundary | [E-utilities documentation](https://www.ncbi.nlm.nih.gov/books/NBK25497/) | 2026-08-09 |

## Network and data boundary

The user's explicit request to retrieve or resolve a small public record set
authorizes the targeted anonymous read and requested public download. No second
confirmation, provider configuration, or credential prompt is required. The
Skill accepts at most 20 source identifiers, 5 requests, and 16 MiB of accepted
responses for one invocation; provider and shared-connector limits may be
stricter.

Invoke the shared connector with `--max-bytes 16777216`. Count each HTTP
response, including pagination, against the five-request Skill limit and stop
before a sixth. Record the redacted exact request URL and parameters for every
accepted response.

Only public identifiers, query terms, taxon, selected fields, and pagination
parameters may be sent. Sensitive, patient, private, unpublished, and
controlled identifiers must not be sent. Paid providers are not fallbacks.
Arbitrary hosts, uploads, remote writes, full-database downloads, POST batches,
and asynchronous or bulk ID-mapping jobs are outside this Skill.

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
read. If a confirmation condition would change the request into a sensitive,
paid, bulk, or remote-job operation, disclose the exact provider, data, scope,
destination, credential, and billing boundary first; this Skill still does not
execute excluded bulk or job paths. On missing adapters, unavailable network,
provider failure, truncation, or missing authorization, degrade honestly and
never claim a call.

## Verification status

- Mode: `not-performed`
- Reason: This instruction-only preview did not execute exact-package routing, provider selection, live retrieval, pagination, response normalization, or scientific benchmarking.
- Relevant versions: UniProt REST rolling / release 2026_02, Ensembl REST 15.12, NCBI E-utilities rolling, Bio 02 shared public connector 0.4.1 contract.
- Unverified boundaries:
  - Exact-package provider selection, pagination, rate limiting, release capture, and identifier normalization have not been runtime-evaluated.
  - One-to-many, deprecated, replaced, malformed, rate-limited, and oversized live responses remain unverified for this exact package.
  - Asynchronous and bulk ID mapping, full-database downloads, uploads, and private or controlled records are outside this preview.

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
