# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`sequence-io-and-transformation`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare input and output formats, alphabet, quality encoding, genetic code, frame, and identifier policy when applicable
- Report metadata or quality information lost by a conversion
- Re-read transformed output and verify record count, identifiers, lengths, and declared round-trip invariants
- Route similarity search and sequence alignment to their owning Skills

## Optional adapters

- `Biopython`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Biopython | 1.87 | [Bio.SeqIO and sequence transformation APIs](https://biopython.org/docs/1.87/api/Bio.SeqIO.html) | 2026-08-08 |

## Network and data boundary

Local file transformations are offline and need no database. Accession retrieval or hosted conversion uploads require explicit authorization and versioned retrieval metadata.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `not-performed`
- Reason: The first preview ships an instruction contract only; no local FASTA/FASTQ transformation adapter is bundled or runtime-tested.
- Relevant versions: Biopython 1.87 reviewed; not executed
- Unverified boundaries:
  - FASTA/FASTQ round-trip behavior and quality-encoding edge cases have not been runtime-tested
  - Multi-gigabyte streaming, hosted conversion services, and batch performance have not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
