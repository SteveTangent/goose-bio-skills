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

The user's explicit search request authorizes the targeted public read and
bounded result download above. Anonymous access requires no provider
configuration or optional API key. Confirm only an unrequested bulk expansion,
sensitive upload, remote job, credential-required path, paid use, or non-default
host.

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
- Reason: Native-tool installation, large fingerprint indexes, 3D workflows, and live PubChem/ChEMBL structure queries were not run.
- Relevant versions: RDKit 2026.03.4, Datamol 0.12.5, PubChem PUG REST rolling, ChEMBL 37
- Unverified boundaries:
  - Large local fingerprint indexes, native builds, and 3D search behavior have not been evaluated
  - PubChem and ChEMBL rate limits, live results, billing or access changes, and confidential-query handling have not been runtime-tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
