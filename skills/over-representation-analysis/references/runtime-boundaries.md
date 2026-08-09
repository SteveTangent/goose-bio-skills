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

Prefer local versioned GMT, GAF, and mapping files. QuickGO, Enrichr, or KEGG calls send gene lists, organism, and query parameters; sensitive lists stay local. KEGG access terms and rate limits must be checked before use.

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
- Reason: Full gene-set catalogs, online identifier mapping, multi-organism databases, R/Rust dependencies, and batch enrichment were not staged.
- Relevant versions: GO 2026-06-19, Reactome V97, WikiPathways 20260710, KEGG 119.0, GSEApy 1.3.0, clusterProfiler 4.20.0
- Unverified boundaries:
  - Full database downloads, online identifier mapping, multi-organism catalogs, and batch-scale ORA have not been run
  - Live QuickGO, Enrichr, and KEGG results and rate or license constraints have not been evaluated by the package

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
