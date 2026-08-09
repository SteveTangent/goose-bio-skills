# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`protein-structure-retrieval-and-comparison`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record accession, entry or model version, experimental or predicted status, assembly, chain, residue mapping, retrieval date, and file hash
- Separate experimental resolution from AlphaFold pLDDT and PAE confidence
- Accept local PDB or mmCIF files with hashes as first-class inputs
- Declare atom selection, mapping, aligned range, missing residues, and pairwise metric
- Exclude structural database search, new prediction, docking, and molecular dynamics

## Optional adapters

- `RCSB PDB`
- `AlphaFold Database`
- `Biopython Bio.PDB.Superimposer`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| RCSB PDB | entry-specific version; weekly archive updates | [REST /rest/v1/core rolling archive API](https://data.rcsb.org/) | 2026-08-08 |
| AlphaFold Database | v6 aligned with UniProt 2025_03 | [prediction file and API schema](https://www.ebi.ac.uk/pdbe/news/alphafold-database-release-notes) | 2026-08-08 |
| Biopython Bio.PDB.Superimposer | Biopython 1.87 | [local pairwise atom superposition](https://biopython.org/docs/1.87/api/Bio.PDB.Superimposer.html) | 2026-08-08 |

## Network and data boundary

Online PDB and AlphaFold DB retrieval requires network access and sends accession queries. Fixed local structure files can be compared offline; record exact archive/model version and hash.

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
- Reason: Live archive retrieval and local pairwise structure superposition were not run.
- Relevant versions: RCSB PDB rolling API, AlphaFold DB v6, Biopython 1.87
- Unverified boundaries:
  - Live RCSB PDB and AlphaFold DB retrieval has not been executed by this package
  - Local PDB/mmCIF parsing, atom selection, residue mapping, and pairwise superposition have not been runtime-tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
