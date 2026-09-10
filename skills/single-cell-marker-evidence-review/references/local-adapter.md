# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: review_marker_evidence.py [-h] [--self-test] [--markers MARKERS]
                                 [--reference REFERENCE] [--output OUTPUT]
                                 [--taxon TAXON] [--tissue TISSUE]
                                 [--namespace NAMESPACE] [--alpha ALPHA]
                                 [--min-support MIN_SUPPORT]

Compare cluster markers with a declared local reference; return candidate
evidence, not automatic labels.

options:
  -h, --help            show this help message and exit
  --self-test
  --markers MARKERS
  --reference REFERENCE
  --output OUTPUT
  --taxon TAXON
  --tissue TISSUE
  --namespace NAMESPACE
  --alpha ALPHA
  --min-support MIN_SUPPORT
```

Input: Marker TSV cluster/gene_id/score/padj; reference TSV taxon/tissue/namespace/cell_type/gene_id/role (support or conflict); optional measured mean_expression/fraction_expressing.

Output: JSON with supporting/conflicting genes, coverage, candidates, ambiguous/unknown states and untouched original clusters.

Exclusions: Automatic final labels, reference downloads, cross-species mapping, atlas integration and diagnostic classification.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
