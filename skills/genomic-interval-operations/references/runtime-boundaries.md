# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`genomic-interval-operations`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare assembly, contig dictionary and order, zero- or one-based origin, half-open or closed intervals, and strand policy
- Define bookended merge, nearest-tie, overlap, and missing-contig behavior before execution
- Reject mixed builds or contig conventions unless an explicit conversion is separately performed
- Treat chrom sizes and genome-order files as hash-bound data dependencies

## Optional adapters

- `bedtools`
- `Gtars`
- `polars-bio`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| bedtools | 2.31.1 | [interval intersect, merge, subtract, closest, and coverage](https://github.com/arq5x/bedtools2/releases) | 2026-08-08 |
| Gtars | core 0.9.0; Python/R 0.9.2; component versions differ | [component-specific interval bindings](https://github.com/databio/gtars/releases) | 2026-08-08 |
| polars-bio | 0.28.0 | [DataFrame interval operations](https://github.com/biodatageeks/polars-bio/releases) | 2026-08-08 |

## Network and data boundary

Local interval algebra is offline and database-free. Remote reference, refget, or object-storage inputs require explicit network authorization and versioned data identity.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Whole-genome joins, distributed/cloud tables, remote refget, and performance comparisons were not run.
- Relevant versions: bedtools 2.31.1, Gtars core 0.9.0 / Python-R 0.9.2, polars-bio 0.28.0
- Unverified boundaries:
  - Whole-genome large joins, cloud or distributed tables, and performance scaling have not been evaluated
  - Cross-engine result equivalence outside the declared coordinate contract is not established

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
