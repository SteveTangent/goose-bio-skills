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

The user's explicit enrichment request authorizes targeted public library reads
and bounded downloads. Anonymous access requires no provider configuration or
optional API key. Confirm an unrequested bulk expansion, sensitive upload,
remote enrichment job, credential-required path, paid use, or non-default host.

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
- Reason: Large permutation runs, full catalogs, multi-core execution, and R/Rust source builds were not run.
- Relevant versions: GSEApy 1.3.0, clusterProfiler 4.20.0, GO 2026-06-19, Reactome V97, WikiPathways 20260710, KEGG 119.0
- Unverified boundaries:
  - Large permutation counts, full catalogs, multi-core scaling, and dependency source builds have not been evaluated
  - Live Enrichr or other rolling gene-set services are outside the reproducible preview path

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
