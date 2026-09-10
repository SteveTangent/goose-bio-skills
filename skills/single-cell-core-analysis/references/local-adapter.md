# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, AnnData, NumPy, SciPy, h5py, Scanpy, igraph. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: run_single_cell.py [-h] [--self-test] [--input INPUT]
                          [--qc-report QC_REPORT] [--output OUTPUT]
                          [--counts-layer COUNTS_LAYER]
                          [--sample-column SAMPLE_COLUMN] [--hvg HVG]
                          [--pcs PCS] [--neighbors NEIGHBORS]
                          [--resolution RESOLUTION] [--seed SEED]
                          [--marker-count MARKER_COUNT]

Small RNA Scanpy baseline using a matching QC receipt.

options:
  -h, --help            show this help message and exit
  --self-test
  --input INPUT
  --qc-report QC_REPORT
  --output OUTPUT
  --counts-layer COUNTS_LAYER
  --sample-column SAMPLE_COLUMN
  --hvg HVG
  --pcs PCS
  --neighbors NEIGHBORS
  --resolution RESOLUTION
  --seed SEED
  --marker-count MARKER_COUNT
```

Input: Checked h5ad and matching qc.json; preserved counts layer; explicit HVG/PCA/neighbors/resolution/seed settings.

Output: Processed object, embedding.tsv, descriptive cluster-vs-rest markers.tsv and analysis.json with actual settings/versions.

Exclusions: Batch integration, automatic annotation, trajectory/velocity, GPU/distributed workflows and condition-level DE.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits. h5ad adapters support up to 5,000 cells, 30,000 genes and ten million cell-feature entries; use trusted local h5ad files. Scanpy uses RNA normalization to 10,000 counts then log1p, Seurat-flavor HVG selection, ARPACK PCA, sklearn neighbors, seeded UMAP and igraph Leiden. It preserves the named counts layer. Do not reuse this RNA recipe for another assay.
