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

The user's explicit retrieval request authorizes targeted public reads and
bounded structure downloads. Anonymous access requires no provider
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
- Reason: Live archive retrieval and local pairwise structure superposition were not run.
- Relevant versions: RCSB PDB rolling API, AlphaFold DB v6, Biopython 1.87
- Unverified boundaries:
  - Live RCSB PDB and AlphaFold DB retrieval has not been executed by this package
  - Local PDB/mmCIF parsing, atom selection, residue mapping, and pairwise superposition have not been runtime-tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
