# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`molecule-standardization-and-descriptors`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Fix fragment, charge and protonation, tautomer, stereochemistry, aromaticity, and descriptor policies
- Preserve original molecule records and a complete transformation log
- Prefer a directly versioned RDKit core; keep Datamol optional until the exact combination is tested
- Do not infer biological activity, efficacy, or mechanism from standardized structures or descriptors

## Optional adapters

- `RDKit`
- `Datamol`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| RDKit | 2026.03.4 | [molecule parsing, standardization, and descriptors](https://github.com/rdkit/rdkit/releases) | 2026-08-08 |
| Datamol | 0.12.5; official tested RDKit range is older | [optional standardization helpers](https://github.com/datamol-io/datamol/releases) | 2026-08-08 |

## Network and data boundary

RDKit and Datamol local transforms are offline. Remote metadata enrichment is outside this standardization contract and must route separately.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: RDKit/Datamol transformation, compatibility checks, and descriptor calculation were not run.
- Relevant versions: RDKit 2026.03.4, Datamol 0.12.5
- Unverified boundaries:
  - The Datamol 0.12.5 and RDKit 2026.03.4 combination is not claimed compatible without a separate test
  - Large molecular files, native builds, and descriptor batch behavior have not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
