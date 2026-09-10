# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, NumPy, Matplotlib. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: plot_results.py [-h] [--self-test]
                       [--kind {volcano,pca,heatmap,groups,correlation,concordance,marker-dot,generic-volcano,embedding}]
                       [--de-report DE_REPORT] [--matrix MATRIX]
                       [--counts COUNTS] [--metadata METADATA]
                       [--output OUTPUT] [--title TITLE]
                       [--matrix-scale {log2-normalized,vst,rlog}]
                       [--significance {pvalue,padj}] [--alpha ALPHA]
                       [--effect-threshold EFFECT_THRESHOLD]
                       [--top-features TOP_FEATURES]
                       [--feature-scale {center,zscore}] [--result RESULT]
                       [--outcome OUTCOME] [--x-variable X_VARIABLE]
                       [--y-variable Y_VARIABLE] [--effect-label EFFECT_LABEL]

Export a bounded volcano plot, PCA or heatmap with its data and declared
settings.

options:
  -h, --help            show this help message and exit
  --self-test
  --kind {volcano,pca,heatmap,groups,correlation,concordance,marker-dot,generic-volcano,embedding}
  --de-report DE_REPORT
  --matrix MATRIX
  --counts COUNTS
  --metadata METADATA
  --output OUTPUT
  --title TITLE
  --matrix-scale {log2-normalized,vst,rlog}
  --significance {pvalue,padj}
  --alpha ALPHA
  --effect-threshold EFFECT_THRESHOLD
  --top-features TOP_FEATURES
  --feature-scale {center,zscore}
  --result RESULT
  --outcome OUTCOME
  --x-variable X_VARIABLE
  --y-variable Y_VARIABLE
  --effect-label EFFECT_LABEL
```

Input: Existing result JSON or explicitly mapped TSV; plot question, scales, significance/direction and display choices.

Output: New PNG/SVG, exact plot-data.tsv and figure.json with source hashes, settings and limitations.

Exclusions: Invented values, silent scale conversion, automatic feature fishing, biological conclusions and new statistical tests.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
