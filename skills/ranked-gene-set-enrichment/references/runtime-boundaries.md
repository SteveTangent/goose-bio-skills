# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`ranked-gene-set-enrichment`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record the ranking statistic, direction, duplicate-gene policy, tie handling, and complete ranked input
- For preranked input use gene-set permutation only, with permutation count and random seed
- Phenotype permutation requires an expression matrix and sample labels and must route to a separate phenotype-aware contract
- Use a local versioned gene-set snapshot for reproducible execution
- Do not convert a complete ranking into cutoff-based ORA or hide permutation uncertainty

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
| Gene Ontology | 2026-06-19 | [versioned ontology and annotation releases](https://release.geneontology.org/) | 2026-08-08 |
| Reactome | V97 | [versioned pathway release](https://reactome.org/download/current/) | 2026-08-08 |
| WikiPathways | 20260710 | [versioned pathway release](https://data.wikipathways.org/20260710/) | 2026-08-08 |
| KEGG | 119.0 | [database release notes](https://www.kegg.jp/kegg/docs/relnote.html) | 2026-08-08 |
| GSEApy | 1.3.0 | [preranked gene-set enrichment](https://gseapy.readthedocs.io/en/latest/) | 2026-08-08 |
| clusterProfiler | 4.20.0 with Bioconductor 3.23/R 4.6 | [R/Bioconductor ranked enrichment](https://bioconductor.org/packages/release/bioc/html/clusterProfiler.html) | 2026-08-08 |

## Network and data boundary

The reproducible core is local with versioned ranking and GMT files. Optional online library discovery sends identifiers and is not a substitute for a fixed execution snapshot.

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
- Reason: Large permutation runs, full catalogs, multi-core execution, and R/Rust source builds were not run.
- Relevant versions: GSEApy 1.3.0, clusterProfiler 4.20.0, GO 2026-06-19, Reactome V97, WikiPathways 20260710, KEGG 119.0
- Unverified boundaries:
  - Large permutation counts, full catalogs, multi-core scaling, and dependency source builds have not been evaluated
  - Live Enrichr or other rolling gene-set services are outside the reproducible preview path

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
