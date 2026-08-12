# Runtime and scientific boundaries

This reference defines the boundary for `public-orthology-retrieval-and-qc`
version `0.7.0`. Ensembl interfaces were reviewed on 2026-08-12; no live canary,
exact-package runtime evaluation, or scientific benchmark was performed.

## Scientific contract

- Accept one to five exact public Ensembl gene stable IDs from one explicit
  source species and one explicit target species. This preview allows only the
  canonical production names `homo_sapiens`, `mus_musculus`,
  `rattus_norvegicus`, and `danio_rerio`, with the matching reviewed gene-ID
  prefixes `ENSG`, `ENSMUSG`, `ENSRNOG`, and `ENSDARG`.
- Treat every returned relationship, type, taxonomy level, method, and
  confidence value as an Ensembl Compara assertion for the accessed service.
- Preserve provider types such as `ortholog_one2one`, `ortholog_one2many`, and
  `ortholog_many2many` literally. Report the type separately from the distinct
  target count returned for the source ID.
- Preserve every field exposed by the condensed JSON response. For expected QC
  concepts not exposed by that response, record `not-exposed`; never invent,
  derive, or upgrade confidence from identity or relationship type.
- Orthology does not establish conserved function, phenotype, mechanism, or
  clinical relevance. Keep de novo inference and gene-tree analysis outside.

## Exact request contract

Use the repository shared connector with provider `ensembl-rest`; it accepts
anonymous JSON `GET` responses only from the allowlisted Ensembl host. For each
input construct exactly:

```text
https://rest.ensembl.org/homology/id/{source_species}/{gene_id}?target_species={target_species}&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json
```

Source and target species must be different members of the four-name preview
allowlist, and the source ID must have its reviewed matching gene prefix. The
connector rejects aliases, extra, duplicate, encoded, uppercase, or changed
query fields. Do not remove a stable-ID version,
replace an ID, retry against another species, call a symbol endpoint, or bypass
the connector with a direct HTTP client.

Example:

```text
python3 scripts/run_research_connector.py \
  --provider ensembl-rest \
  --url 'https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?target_species=mus_musculus&type=orthologues&sequence=none&aligned=0&format=condensed&content-type=application/json' \
  --output tp53-mouse-orthology.json \
  --max-bytes 16777216
```

The output path must be new. A successful checked response with an empty
`homologies` collection is `no-ortholog-returned`, not proof that the source ID
does not exist. An absent input object, provider error envelope, invalid JSON,
or failed request remains distinct.

### Response and QC contract

For each input preserve the top-level input identifier and all homology records
in their provider order. From every returned record preserve, when present:

- provider relationship `type`, `method_link_type`, and `taxonomy_level`
- all source and target objects, especially their `id`, `species`, and any
  exposed version or release metadata
- all exposed relationship cardinality, identity, positivity, tree-compliance,
  GOC, WGA, and high-confidence fields using their exact provider names/values

Compute only `returned_target_count` as the number of distinct returned target
IDs for that input. This is an observation, not a replacement for the provider
relationship type. If a named QC concept is absent, emit `not-exposed`; do not
map absence to `false`, `0`, low confidence, or failure. Preserve the raw
response artifact and fingerprint because the exact condensed JSON semantics
were not verified in this preview.

An optional `/archive/id/{gene_id}?content-type=application/json` read through
the same shared connector may add source-ID current/replacement/release metadata.
It is provenance enrichment, not a substitute for service-release metadata and
not required for the MVP result.

## Interface freshness

| Component | Reviewed interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Ensembl REST | API `15.12`; homology-by-species-and-gene `GET`, full or condensed layout | [Homology endpoint](https://rest.ensembl.org/documentation/info/homology_species_gene_id) | 2026-08-12 |
| Ensembl stable-ID archive | `archive/id` exposes source-ID version/current/release metadata | [Archive endpoint](https://rest.ensembl.org/documentation/info/archive_id_get) | 2026-08-12 |
| Ensembl Compara interpretation | relationship types and high-confidence QC concepts | [Homology types](https://www.ensembl.org/info/genome/compara/homology_types.html) and [orthology QC](https://www.ensembl.org/info/genome/compara/Ortholog_qc_manual.html) | 2026-08-12 |

Documentation review establishes interface freshness only. It does not prove
live availability, condensed-response field presence, completeness, package
routing, scientific validity, or cross-release stability.

## Network and data boundary

An explicit request to retrieve public orthology records authorizes the targeted
anonymous reads and requested public artifact. No second confirmation or
configuration prompt is required. One invocation accepts at most five source
IDs, five required homology responses, 16 MiB total accepted response data, and
three requests per second. Optional archive lookups count toward a separate
five-response provenance supplement and do not change the core result status.

Use a new output path and `--max-bytes 16777216`; count every response. Record
the exact redacted URL and parameters, access time, HTTP status, response
fingerprint, byte count, and available provider release metadata. Only a checked
live response may support a completed-call claim.

Only public stable IDs, declared species, and fixed response parameters may be
sent. Sensitive, patient, private, unpublished, controlled, or credential-bearing
material must not be sent. Paid services are not fallbacks. Arbitrary hosts,
uploads, remote writes, POST, sequences, bulk harvests, and remote jobs are out.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Network transport follows the host proxy and CA trust policy. On a missing
adapter, unavailable network, provider error, invalid JSON, truncation, rate
limit, or drift, return `needs-tool` or `partial` and never claim completion.

## Verification status

- Mode: `not-performed`
- Reason: no exact-package live canary, semantic condensed-response fixture,
  response normalization run, release capture, or output evaluation was run.
- Relevant versions: Ensembl REST API 15.12 documentation and release 116
  citation guidance checked 2026-08-12; Bio 02 shared connector 0.7.0 contract.
- Unverified boundaries:
  - Live transport, current response schema, empty/error behavior, and the exact
    QC fields exposed by `format=condensed`.
  - Identifier validation, request construction, normalization, target-count
    accounting, provider-field preservation, and release capture end to end.
  - Scientific benchmarking, domain-expert review, functional conservation,
    non-vertebrate divisions, de novo inference, tree analysis, and clinical use.

A connector boundary self-test or documentation check is not a package pass.
This Skill remains `preview + reviewed` until bounded exact-package evidence is
recorded.
