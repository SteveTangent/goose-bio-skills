# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`chemical-similarity-and-substructure-search`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Require an explicitly standardized representation and preserve the original molecule record
- Record fingerprint type and version, radius, bit length, chirality policy, similarity metric, threshold, and reference-library release
- Do not mix PubChem server similarity with an unspecified local RDKit fingerprint score
- Do not infer functional, pharmacological, or clinical equivalence from similarity or substructure matches

## Optional adapters

- `RDKit`
- `Datamol`
- `PubChem PUG REST`
- `ChEMBL REST`
- `ChEMBL 37 bulk release`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| RDKit | 2026.03.4 | [fingerprints, similarity, and substructure search](https://github.com/rdkit/rdkit/releases) | 2026-08-08 |
| Datamol | 0.12.5 | [optional molecule and search convenience layer](https://pypi.org/project/datamol/) | 2026-08-08 |
| PubChem PUG REST | no semantic API version; access-date bound | [rolling structure-query service](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest) | 2026-08-08 |
| ChEMBL REST | unversioned; access-date bound | [rolling structure-query API](https://www.ebi.ac.uk/chembl/api/data/docs) | 2026-08-08 |
| ChEMBL 37 bulk release | 37 | [fixed downloadable database release](https://www.ebi.ac.uk/chembl/beta/) | 2026-08-08 |

## Network and data boundary

RDKit and Datamol local search are offline. PubChem and ChEMBL queries send structures or identifiers; never upload confidential molecules silently and record ChEMBL 37 or the exact access date.

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
- Reason: Native-tool installation, large fingerprint indexes, 3D workflows, and live PubChem/ChEMBL structure queries were not run.
- Relevant versions: RDKit 2026.03.4, Datamol 0.12.5, PubChem PUG REST rolling, ChEMBL 37
- Unverified boundaries:
  - Large local fingerprint indexes, native builds, and 3D search behavior have not been evaluated
  - PubChem and ChEMBL rate limits, live results, billing or access changes, and confidential-query handling have not been runtime-tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
