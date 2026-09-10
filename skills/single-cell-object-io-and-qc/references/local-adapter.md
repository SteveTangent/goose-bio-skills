# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, AnnData, NumPy, SciPy, h5py. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: inspect_single_cell.py [-h] [--self-test] [--input INPUT]
                              [--output OUTPUT] [--counts-layer COUNTS_LAYER]
                              [--sample-column SAMPLE_COLUMN] [--assay ASSAY]
                              [--min-counts MIN_COUNTS]
                              [--min-genes MIN_GENES]
                              [--mitochondrial-prefix MITOCHONDRIAL_PREFIX]
                              [--max-mito-fraction MAX_MITO_FRACTION]

Inspect/filter a small declared raw-count h5ad without modifying inputs.

options:
  -h, --help            show this help message and exit
  --self-test
  --input INPUT
  --output OUTPUT
  --counts-layer COUNTS_LAYER
  --sample-column SAMPLE_COLUMN
  --assay ASSAY
  --min-counts MIN_COUNTS
  --min-genes MIN_GENES
  --mitochondrial-prefix MITOCHONDRIAL_PREFIX
  --max-mito-fraction MAX_MITO_FRACTION
```

Input: Small h5ad; named raw-count layer, sample column, RNA assay, explicit min-counts/min-genes; optional mitochondrial prefix/fraction.

Output: New checked.h5ad, per-cell qc.tsv and qc.json including exact output hash for the core-analysis handoff.

Exclusions: Seurat execution/conversion, doublet detection, ambient-RNA correction, automatic cutoffs, integration and annotation.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits. h5ad adapters support up to 5,000 cells, 30,000 genes and ten million cell-feature entries; use trusted local h5ad files. Scanpy uses RNA normalization to 10,000 counts then log1p, Seurat-flavor HVG selection, ARPACK PCA, sklearn neighbors, seeded UMAP and igraph Leiden. It preserves the named counts layer. Do not reuse this RNA recipe for another assay.
