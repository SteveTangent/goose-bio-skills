# Expression diagnostics

Use the existing --kind pca or heatmap with an explicitly selected feature count and centering policy. The normalized matrix scale must be known; raw counts require the matching DESeq2 report and its size factors. DESeq2-normalized log-count PCA is exploratory, not a substitute for a study-specific variance-stabilizing transformation.

For --kind sample-correlation, choose --top-features and --feature-scale center. The correlation itself deliberately uses selected transformed values before centering, records feature_scale=not-applied, and ranges from -1 to 1. Constant samples yield an explicit failure rather than an invented coefficient. Use identical feature selection when comparing group and batch displays.

PCA, correlation and heatmaps describe patterns. They do not test a treatment effect, prove a sample swap or justify removing an outlier. Show sample IDs, group/batch provenance, scale and selected features. For microarray plots count features/probes separately from genes; do not rename probes as genes merely because the compatibility column is gene_id.
