# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, AnnData, NumPy, SciPy, h5py. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: aggregate_pseudobulk.py [-h] [--self-test] [--input INPUT]
                               [--samples SAMPLES] [--output OUTPUT]
                               [--counts-layer COUNTS_LAYER]
                               [--sample-column SAMPLE_COLUMN]
                               [--cell-type-column CELL_TYPE_COLUMN]
                               [--cell-type CELL_TYPE] [--min-cells MIN_CELLS]
                               [--numerator NUMERATOR]
                               [--denominator DENOMINATOR]
                               [--independent-samples-declared]

Aggregate one declared cell type by biological sample using raw counts.

options:
  -h, --help            show this help message and exit
  --self-test
  --input INPUT
  --samples SAMPLES
  --output OUTPUT
  --counts-layer COUNTS_LAYER
  --sample-column SAMPLE_COLUMN
  --cell-type-column CELL_TYPE_COLUMN
  --cell-type CELL_TYPE
  --min-cells MIN_CELLS
  --numerator NUMERATOR
  --denominator DENOMINATOR
  --independent-samples-declared
```

Input: Small h5ad counts layer, biological sample_id and reviewed cell_type; samples.tsv sample_id/condition; one type, min-cells and contrast.

Output: New counts.tsv and samples.tsv plus aggregation.json with count conservation, cell counts, exclusions and downstream readiness.

Exclusions: Paired/longitudinal designs, normalized-count summation, condition DE, automatic labels and multiple-cell-type inference.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits. h5ad adapters support up to 5,000 cells, 30,000 genes and ten million cell-feature entries; use trusted local h5ad files. Scanpy uses RNA normalization to 10,000 counts then log1p, Seurat-flavor HVG selection, ARPACK PCA, sklearn neighbors, seeded UMAP and igraph Leiden. It preserves the named counts layer. Do not reuse this RNA recipe for another assay.
