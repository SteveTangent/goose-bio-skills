# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`over-representation-analysis`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare organism, identifier namespace and mapping, selected set, tested universe, and exact gene-set release or digest
- Use a one-sided over-representation test under an explicit contingency-table contract
- Define the multiplicity family before adjusted results and route adjustment to the shared statistical contract
- Do not substitute a full ranking for the selected-set ORA contract

## Optional adapters

- `Gene Ontology`
- `Reactome`
- `WikiPathways`
- `KEGG`
- `GSEApy`
- `clusterProfiler`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Gene Ontology | 2026-06-19 | [versioned OBO and annotation releases](https://release.geneontology.org/) | 2026-08-08 |
| Reactome | V97 | [versioned pathway release](https://reactome.org/download/current/) | 2026-08-08 |
| WikiPathways | 20260710 | [versioned pathway release](https://data.wikipathways.org/20260710/) | 2026-08-08 |
| KEGG | 119.0 | [database release notes](https://www.kegg.jp/kegg/docs/relnote.html) | 2026-08-08 |
| GSEApy | 1.3.0 | [ORA execution adapter](https://gseapy.readthedocs.io/en/latest/) | 2026-08-08 |
| clusterProfiler | 4.20.0 with Bioconductor 3.23/R 4.6 | [ORA execution adapter](https://bioconductor.org/packages/release/bioc/html/clusterProfiler.html) | 2026-08-08 |

## Network and data boundary

Prefer local versioned GMT, GAF, and mapping files. QuickGO and KEGG reads send
public identifiers, organism, and query parameters. Enrichr direct reads send
only library, query, or public-result identifiers; gene-list submission is a
separate remote job. Sensitive lists stay local. KEGG terms and rate limits
must be checked before use.

The user's explicit ORA request authorizes targeted public metadata reads and
bounded annotation downloads. Anonymous access requires no provider
configuration or optional API key. Confirm an unrequested bulk expansion,
sensitive upload, remote enrichment job, credential-required path, paid or
licensed use, or non-default host.

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
- Reason: Full gene-set catalogs, online identifier mapping, multi-organism databases, R/Rust dependencies, and batch enrichment were not staged.
- Relevant versions: GO 2026-06-19, Reactome V97, WikiPathways 20260710, KEGG 119.0, GSEApy 1.3.0, clusterProfiler 4.20.0
- Unverified boundaries:
  - Full database downloads, online identifier mapping, multi-organism catalogs, and batch-scale ORA have not been run
  - Live QuickGO, Enrichr, and KEGG results and rate or license constraints have not been evaluated by the package

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
