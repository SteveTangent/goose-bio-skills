# Runtime and scientific boundaries

This reference defines the boundary for
`human-variant-evidence-retrieval` version `0.8.0`. The official ClinVar
programmatic-access, identifier, and VCV data-model guidance was checked on
2026-08-13. This preview does not claim formal exact-package agent runtime or
scientific evaluation. One bounded public record retrieved once by exact VCV
accession and once by numeric Variation ID was used as a developer canary for
the normalizer on 2026-08-13.

## Identifier and record contract

- A VCV accession identifies ClinVar's variant-level aggregate and is constructed
  from the Variation ID with the `VCV` prefix and nine-digit zero padding.
- Numeric identifiers are accepted only when explicitly labeled `Variation ID`;
  ClinVar Allele ID numbers overlap and are not interchangeable.
- A VCV version is material. Preserve it when supplied and reject a payload with
  a different version.
- Preserve each SCV submitter assertion separately. Aggregate classifications,
  review status, and conditions are provider statements, not independent evidence
  of pathogenicity or clinical actionability.

Official references: [programmatic access](https://www.ncbi.nlm.nih.gov/clinvar/docs/programmatic_access/),
[identifiers](https://www.ncbi.nlm.nih.gov/clinvar/docs/identifiers/), and
[ClinVar data model](https://www.ncbi.nlm.nih.gov/clinvar/docs/data_model/).

## Shared live read-only adapter

Use the repository shared connector with provider `ncbi-eutils`. It accepts
anonymous bounded `GET` requests to reviewed NCBI EFetch paths, writes a payload
and provenance sidecar create-new, and does not read provider credentials.

Make exactly one call per requested identifier and stop before a sixth:

```text
python3 scripts/run_research_connector.py \
  --provider ncbi-eutils \
  --url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&rettype=vcv&id=14206&is_variationid=true&from_esearch=true' \
  --max-bytes 16777216 --output 14206.clinvar-vcv.xml
```

For a VCV accession, set `id` to the exact accession or accession.version and
omit `is_variationid` and `from_esearch`. Do not use ESearch, EPost, History
state, free-text terms, other databases, or arbitrary URLs. The normalizer
requires the XML payload and the connector sidecar at
`<payload>.provenance.json`.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

If the connector, network, or provider is unavailable, return `needs-tool` and
the exact dry-run plan. A transport attempt without a checked response is not a
retrieval. Never create a synthetic provider result for the user.

## Normalizer boundary

The standard-library helper:

- accepts one to five regular VCV XML payloads, at most 32 MiB combined with
  provenance;
- opens payloads and provenance sidecars nonblocking, then accepts them only
  after descriptor-level regular-file checks, so FIFOs and other special files
  are rejected before any read;
- accepts UTF-8 XML only and rejects DTD/entity declarations, malformed XML,
  wrong or extra records, mismatched or non-positive VCV/SCV/RCV versions,
  duplicate assertion/SCV/RCV identities, and provider drift in required fields;
- returns a structured `provider-failure` for explicit ClinVar error or warning
  envelopes instead of reporting those responses as missing records;
- checks connector schema, exact request and response fields, timestamps, and
  SHA-256 payload binding before normalization;
- during normal execution, creates one new JSON report through temporary-first,
  no-overwrite publication with precise-inode rollback, confines output to the
  current working directory, rejects parent traversal and symlinked parent
  components through descriptor-relative checks, and never creates directories,
  uses the network, or starts subprocesses; `--self-test` owns and cleans one
  isolated system-temporary fixture directory.

Connector provenance sidecars are unsigned. Structural checks and SHA-256
binding detect inconsistency; they do not cryptographically authenticate who
created a locally supplied sidecar. Retain sidecars directly from the reviewed
connector and do not hand-author them.

The helper preserves selected provider identity, classification, condition,
date, and provenance fields plus complete normalized classification/condition
subtrees. It does not reproduce unrelated observation, citation, or molecular
annotation fields as a complete ClinVar archive substitute.

## Verification status

- Mode: `not-performed`
- Reason: the bundled deterministic official-shape replay self-test and one
  bounded public record retrieved through both exact identifier forms cover the
  normalizer, not formal agent routing, complete live-provider behavior,
  representative scientific use, or human-expert review.
- Relevant interfaces: NCBI ClinVar rolling VCV XML/E-utilities guidance checked
  2026-08-13; Bio 02 shared public connector `0.8.0` contract.
- Unverified boundaries:
  - Agent routing, interactive identifier clarification, and end-to-end output
    review have not been runtime-evaluated.
  - The self-test covers one single-assertion record, one retained conflicting
    aggregate, one empty result, malformed and DTD-bearing XML, strict connector
    metadata, identifier/version drift, duplicate SCV/RCV identities, provenance
    binding, determinism, atomic rollback, and no-overwrite behavior; broader XML
    variants and provider drift remain unevaluated.
  - The developer canary preserved 87 ClinicalAssertions and 17 RCV accessions
    identically for exact VCV and numeric Variation-ID retrieval; other large
    assertion sets, somatic classifications, structural variants, deleted
    records, live not-found behavior, rate limits, and multi-record provider
    failures remain unverified.
  - Free-text resolution, ACMG classification, evidence scoring, conflict
    resolution, diagnosis, treatment, and clinical use are outside this preview.

A skip is not a pass. These helper diagnostics do not establish clinical or
scientific validity.
