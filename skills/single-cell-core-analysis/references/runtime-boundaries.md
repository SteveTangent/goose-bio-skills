# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`single-cell-core-analysis`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Require a validated object, authoritative counts layer, and explicit QC handoff before analysis
- Fix normalization, HVG method, PCA dimensions, neighbor backend, seed, UMAP, clustering algorithm, and resolution
- Do not treat Scanpy and Seurat outputs as numerically interchangeable
- A SingleCellExperiment object may be an input container, but it is not an execution stack for this Skill
- Limit the owned job to an exploratory baseline; exclude integration, annotation, trajectory, and condition-level inference

## Optional adapters

- `Scanpy`
- `AnnData`
- `Seurat`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Scanpy | 1.12.1 | [normalization, HVG, PCA, graph, embedding, and clustering](https://scanpy.readthedocs.io/en/latest/release-notes/index.html) | 2026-08-08 |
| AnnData | 0.13.2 | [input object container for Scanpy execution](https://anndata.readthedocs.io/en/stable/release-notes/) | 2026-08-08 |
| Seurat | 5.5.1 | [exploratory single-cell analysis](https://satijalab.org/seurat/news/) | 2026-08-08 |

## Network and data boundary

Local object analysis is offline. Remote arrays, cloud compute, and hosted embeddings are optional network paths and require explicit authorization.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Object-scale preprocessing, graph construction, embedding, clustering, GPU, and distributed paths were not run.
- Relevant versions: Scanpy 1.12.1 + AnnData 0.13.2, Seurat 5.5.1
- Unverified boundaries:
  - Normalization, HVG, PCA, graph, UMAP, and clustering were not executed on an exact package fixture
  - GPU, distributed, cloud, integration, annotation, trajectory, and condition-inference paths are outside the reviewed runtime scope

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
