# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`sequence-similarity-and-homology-search`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record query molecule type, engine and version, database release or digest, masking, E-value, coverage, hit cap, and all non-default parameters
- Use a micro database only for installation smoke, never for research interpretation
- For research execution require a question-appropriate complete or curated database fixed by release and digest
- Preserve normalized hits and the raw result artifact
- Do not infer orthology, function, or evolutionary mechanism from similarity alone
- Route downstream pairwise or multiple alignment to the alignment Skill

## Optional adapters

- `NCBI BLAST+`
- `MMseqs2`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| NCBI BLAST+ | 2.17.0 | [command-line local and remote similarity search](https://www.ncbi.nlm.nih.gov/books/NBK131777/) | 2026-08-08 |
| MMseqs2 | 18-8cc5c | [search and database workflow](https://github.com/soedinglab/MMseqs2/releases) | 2026-08-08 |

## Network and data boundary

Fixed local databases can be searched offline. Remote BLAST and database downloads require network access; disclose the provider, query sequence data, database release, and retrieval date.

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
- Reason: Full reference databases, indexing, remote live databases, GPU/MPI execution, and large searches were not staged for this preview.
- Relevant versions: NCBI BLAST+ 2.17.0, MMseqs2 18-8cc5c, reference databases not-detected
- Unverified boundaries:
  - NR, NT, UniRef, and other full-database downloads and indexes have not been built or searched
  - Remote BLAST, GPU, MPI, and large-scale result stability have not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
