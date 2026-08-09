# Public research connectors

Bio 02 can make bounded `GET` and `HEAD` requests to reviewed public research
services. Public, no-key access is the default. Users do not need a provider
configuration file or a confirmation token for ordinary public queries and small
downloads.

`providers.json` is an internal execution policy, not user configuration. Each
entry fixes:

- whether access is direct read-only, terms-restricted, a conditional remote job,
  or disabled;
- exact HTTPS URL prefixes and hosts;
- request rate and maximum response size;
- credential, billing, and provider-documentation boundaries.

The shared standard-library executor is
`../scripts/run_research_connector.py`.

## Current execution boundary

| Access | Services | Behavior |
|---|---|---|
| Direct public read | NCBI EInfo/ESearch/ESummary/EFetch without History state, UniProt REST, Ensembl REST, Europe PMC, BioStudies, RCSB PDB, AlphaFold DB, synchronous PubChem PUG REST, ChEMBL, anonymous Crossref, QuickGO, public Enrichr GET paths | Execute bounded `GET` or `HEAD` without a key |
| Terms-restricted read | KEGG REST | Requires `--acknowledge-terms`; academic-use terms still apply |
| Conditional remote job | EMBL-EBI Job Dispatcher, NCBI Remote BLAST | Not implemented by this read-only executor; it never uploads a sequence or claims a job was submitted |
| Commercial or paid | None | Paid and metered services are excluded from the executable catalog |

Enrichr gene-list submission is a write/upload action and is not covered by its
public GET boundary. Similarly, UniProt ID-mapping submission is not covered by
the read-only executor. NCBI EPost, ESearch History writes, and PubChem queued,
ListKey, or CacheKey operations are also excluded because a `GET` can create
remote state on those paths.

## Examples

Retrieve one public UniProt record:

```text
python3 scripts/run_research_connector.py \
  --provider uniprot-rest \
  --url 'https://rest.uniprot.org/uniprotkb/P04637.json' \
  --output P04637.uniprot.json
```

Search PubMed without an API key:

```text
python3 scripts/run_research_connector.py \
  --provider ncbi-eutils \
  --url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=BRCA1&retmode=json&retmax=20' \
  --output brca1-pubmed.json
```

The shared executor is deliberately anonymous-only. It does not read NCBI,
Crossref, or other contact, API-key, token, or paid-credential environment
variables, and it rejects credential or contact query parameters in `--url`.
A user-supplied host adapter may manage identity separately after disclosing its
provider, data, credential, storage, and billing boundary; that adapter is not
this shared executor.

For APIs with numeric pagination, the executor can issue a bounded sequence and
atomically write one JSON bundle:

```text
python3 scripts/run_research_connector.py \
  --provider ebi-biostudies \
  --url 'https://www.ebi.ac.uk/biostudies/api/v1/search?query=liver&pageSize=20' \
  --pages 3 \
  --page-param page \
  --page-start 1 \
  --output liver-biostudies-pages.json
```

Cursor pagination remains provider-specific and is not guessed by the shared
executor.

## Safety and provenance

The executor:

- accepts only `GET` and `HEAD`;
- rejects arbitrary hosts, unreviewed path prefixes, URL credentials, path
  traversal, non-HTTPS URLs, and redirect escapes;
- caps pagination at 20 pages, timeout at 120 seconds, retries at four, and total
  bytes at the lower of the CLI request and provider limit;
- retries only transient network failures and HTTP `429/5xx` responses;
- treats only HTTP `200` or `204` as a completed response, rejects asynchronous
  `202` and partial `206`, and verifies a declared response length before
  publication;
- creates new files only and never overwrites an existing payload or provenance
  file;
- publishes payload and provenance through same-directory temporary files and
  no-clobber hard links, rolling back its own first file if the pair cannot be
  completed;
- records provider, redacted URLs, response status, timestamps, byte count, and
  SHA-256 digest in `<output>.provenance.json`;
- emits a completed result with `network_performed=true` only after a checked
  response and both output files are published. A failed event reports whether a
  network attempt began, so it can be `true` without a success artifact.

Large datasets, bulk raw reads, whole database snapshots, paid APIs, arbitrary
URLs, private studies, controlled data, and remote write/job submission are
outside this layer.

## Deterministic self-test

```text
python3 scripts/run_research_connector.py --self-test
```

The self-test makes no network request. It covers the catalog policy, UniProt
allowlist, real redirect-handler rejection, NCBI History and PubChem asynchronous
path rejection, paid/job boundaries, KEGG terms gate, anonymous-only behavior,
HTTP `202`, short bodies, retries, byte limits, temporary-file cleanup, and
atomic create-new publication with existing-file preservation.
