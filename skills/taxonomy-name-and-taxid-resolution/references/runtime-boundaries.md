# Runtime and scientific boundaries

This reference defines the operating boundary for
`taxonomy-name-and-taxid-resolution` version `0.6.0`. NCBI interfaces were
reviewed on 2026-08-10; this preview does not claim that the exact Skill was
runtime-evaluated.

## Scientific contract

- Use NCBI Taxonomy database `taxonomy`; do not substitute a gene, nucleotide, or protein namespace.
- Call the returned `ScientificName` the NCBI current scientific name. It is not a universal nomenclatural judgment.
- Preserve every exact name match and each returned name class. Common names, synonyms, misspellings, authority strings, and equivalent names are not interchangeable.
- Treat `LineageEx` as NCBI's current classification, not a phylogenetic tree.
- Call a requested TaxId merged or secondary only when EFetch returns a different current `TaxId` and lists the request under `AkaTaxIds`.
- A non-returned TaxId is `not-returned`; this bounded interface alone does not prove it was deleted.

## Shared live read-only adapter

Use the repository's shared connector with provider `ncbi-eutils`. It accepts
allowlisted anonymous `GET` or `HEAD` requests, although this workflow uses
`GET` only. It does not accept arbitrary URLs, credentials, contact identities,
POST, or EPost. This Skill does not authorize History Server state.

For each literal name, percent-encode the value and use one exact-name request:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=taxonomy&term=%22Homo%20sapiens%22%5BAll%20Names%5D&retmode=json&retmax=20&retstart=0
```

Omit `usehistory` entirely; do not add `WebEnv` or `query_key`. A 2026-08-10
interface check found that even explicit `usehistory=n` returned a WebEnv and
query key, while omission did not. Preserve `count`, `idlist`, and
`querytranslation`. If `count` exceeds `retmax`, stop with `partial`; do not
silently treat the first page as complete.

Fetch at most 20 unique direct and candidate TaxIds in one request:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=taxonomy&id=9606%2C74465&retmode=xml
```

Read `TaxId`, `ScientificName`, every direct and classed child of `OtherNames`,
`Rank`, `LineageEx`, `AkaTaxIds`, and available dates. Match a name input to the
returned current and secondary names after trimming and case-folding only; do
not perform fuzzy or punctuation-changing normalization.

Example connector invocation:

```text
python3 scripts/run_research_connector.py \
  --provider ncbi-eutils \
  --url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=taxonomy&id=9606%2C74465&retmode=xml' \
  --output taxonomy-records.xml \
  --max-bytes 16777216
```

The output path must be new. The connector writes the response and a companion
provenance JSON file; use only a checked live response to claim network
execution.

## Interface freshness

| Component | Reviewed interface | Official documentation | Checked |
| --- | --- | --- | --- |
| NCBI E-utilities | rolling API; `taxonomy` ESearch and EFetch | [E-utilities reference](https://www.ncbi.nlm.nih.gov/books/NBK25497/) and [parameter reference](https://www.ncbi.nlm.nih.gov/books/NBK25499/) | 2026-08-10 |
| NCBI Taxonomy model | current scientific names, secondary names/TaxIds, ranks, and lineage | [Taxonomy overview](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/data-processing/taxonomy-processing/taxonomy/) | 2026-08-10 |

A supporting connector check on 2026-08-10 observed current Taxonomy EInfo
fields `Scientific Name`, `Synonym`, and `All Names`; exact `All Names` search;
and EFetch XML in which secondary TaxId `74465` resolved to current TaxId
`2771340` with `AkaTaxIds`. This is interface freshness evidence, not exact-Skill
routing, normalization, or output evaluation.

NCBI's current E-utility guidance says requests should include `tool` and
`email`, and recommends an API key above three requests per second. The shared
connector deliberately has no contact or credential surface, sends neither,
and caps anonymous use at three requests per second. This preview therefore
does not claim conformance with that contact-identification recommendation. Do
not bypass the connector by adding an email or API key to a URL; any future
identified-client support belongs in a reviewed shared adapter.

## Network and data boundary

An explicit request to resolve a small set of public names or TaxIds authorizes
the targeted anonymous reads and requested public output. No second
confirmation or configuration prompt is required. One invocation accepts at
most 20 total inputs, including no more than four names; no more than 20
candidate TaxIds, five HTTP responses, 16 MiB of accepted responses, or three
requests per second.

Only literal public taxon names, public TaxIds, and bounded retrieval parameters
may be sent. Sensitive, patient, private, unpublished, and controlled material
must not be sent. Paid services are not fallbacks. Arbitrary hosts, uploads,
remote writes, POST, History Server state, fuzzy searches, descendant or
subtree enumeration, full taxdump downloads, gene-ID mapping, and remote jobs
are outside this Skill.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Network transport follows the agent host's proxy and CA trust policy. On a
missing adapter, unavailable network, error envelope, truncation, or provider
failure, return `needs-tool` or `partial` and never claim a completed call.

## Verification status

- Mode: `not-performed`
- Reason: this instruction-only preview did not execute exact-package routing, literal-query construction, response normalization, ambiguity handling, or output generation.
- Relevant versions: NCBI E-utilities rolling API and Taxonomy fields checked 2026-08-10; Bio 02 shared public connector 0.6.0 contract.
- Unverified boundaries:
  - Exact-package literal-query construction, ambiguity handling, response normalization, name-class extraction, and merged TaxId mapping have not been runtime-evaluated.
  - More-than-20 matches, deleted or unavailable TaxIds, malformed records, rate limits, provider drift, and oversized responses remain unverified for this exact package.
  - Gene-ID mapping, fuzzy name search, descendant expansion, taxdump downloads, phylogeny, and clinical use are outside this preview.

A supporting interface check is not a package pass. The Skill remains
`preview + reviewed` until bounded exact-package evaluation is recorded.
