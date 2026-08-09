# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`single-cell-object-io-and-qc`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record the object and file version, axes, assays, layers, authoritative counts source, sparse or backed state, and duplicate-ID policy
- Inventory conversion losses for assays, layers, categories, graphs, sparse types, and provenance
- Default QC to reporting metrics and recommendations rather than silently filtering cells
- Treat AnnData 0.13 copy-on-write, layers[None], and Zarr changes as an explicit compatibility boundary

## Optional adapters

- `AnnData`
- `Scanpy`
- `Seurat`
- `SingleCellExperiment`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| AnnData | 0.13.2 | [single-cell object I/O](https://anndata.readthedocs.io/en/stable/release-notes/) | 2026-08-08 |
| Scanpy | 1.12.1 | [single-cell QC metrics](https://scanpy.readthedocs.io/en/latest/release-notes/index.html) | 2026-08-08 |
| Seurat | 5.5.1 | [Seurat object schema and QC](https://satijalab.org/seurat/news/) | 2026-08-08 |
| SingleCellExperiment | 1.34.0 with Bioconductor 3.23 | [Bioconductor single-cell object contract](https://bioconductor.org/packages/release/bioc/html/SingleCellExperiment.html) | 2026-08-08 |

## Network and data boundary

Local object I/O and QC are offline. Remote object stores or cloud-backed arrays are optional network paths and require explicit data and credential disclosure.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Large, backed, Zarr, and cross-ecosystem object loading and conversion were not run.
- Relevant versions: AnnData 0.13.2, Scanpy 1.12.1, Seurat 5.5.1, SingleCellExperiment 1.34.0 / Bioconductor 3.23
- Unverified boundaries:
  - Large, backed, sparse, and Zarr object behavior has not been evaluated
  - AnnData, Seurat, and SingleCellExperiment cross-conversion loss and compatibility have not been runtime-tested

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
