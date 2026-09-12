# Protein and distance smoke examples

Original deterministic synthetic data (Apache-2.0), no patient/public study data.
100 protein rows × 8 samples; numeric-looking identifiers deliberately retain
leading zeros. Two independent groups and a crossed categorical batch. Values
are synthetic log2 measurements, not a recommendation to normalize real data
this way. All fixtures together are below 20 KB. Distance examples have 8 samples.

Run from a new analysis directory after copying these fixture TSVs. Set the
helper path to the corresponding installed package. Each output name must be new.

```text
python3 QC/scripts/check_protein_table.py --matrix proteins.tsv --samples samples.tsv --output qc --feature-level protein --scale log2-normalized --normalization-method synthetic --unit log2-intensity --zero-semantics value --batch-status recorded --independent --numerator treated --denominator control
python3 MODEL/scripts/run_limma.py --matrix qc/model-matrix.tsv --metadata qc/model-samples.tsv --output protein.json --numerator treated --denominator control --covariate-column batch --declared-protein-level-normalized-log2
python3 PLOT/scripts/plot_results.py --kind volcano --de-report protein.json --significance padj --alpha 0.05 --effect-threshold 1 --output volcano
python3 PLOT/scripts/plot_results.py --kind pca --de-report protein.json --matrix qc/model-matrix.tsv --matrix-scale log2-normalized --metadata groups.tsv --top-features 100 --feature-scale center --output protein-pca
python3 REPORT/scripts/build_analysis_report.py --report qc=qc/qc.json model=protein.json --figure volcano=volcano pca=protein-pca --output protein-report --language zh
python3 PCOA/scripts/run_pcoa.py --distances euclidean.tsv --format square-tsv --metric euclidean --metadata groups.tsv --output pcoa
python3 PLOT/scripts/plot_results.py --kind pcoa --result pcoa/pcoa.json --output ordination
python3 REPORT/scripts/build_analysis_report.py --report ordination=pcoa/pcoa.json --figure ordination=ordination --output distance-report --language zh
```

Protein model: pinned R 4.4.1 / limma 3.60.6; QC standard library, PCoA NumPy,
plots NumPy/Matplotlib. No automatic installation. The existing beta-distance
helper can use counts.tsv with --feature-table and --output beta.json; then use
PCoA --format beta-json --metric bray_curtis. No normalization occurs.

Expected checks: Euclidean distances reconstructed by all positive coordinates;
cycle distances retain negative eigenvalues and have positive-space distortion.
A missing cell, unknown scale or repeated subject blocks protein model export.
An asymmetric/missing distance, zero-depth native pair or mismatched group ID
must fail without filling, recoding or silently dropping samples. Do not infer
biological validity, significance or representative performance from fixtures.
