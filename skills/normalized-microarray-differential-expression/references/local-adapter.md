# One normalized microarray contrast

Run from an analysis directory. Inputs are regular UTF-8 TSVs at most 8 MiB each. Outputs must use a new directory whose parent already exists; symlinks, traversal and overwrite are refused.

Expression: `feature_id` (the GEO preparation format) or `gene_id` followed by 4–32 unique samples and 20–30,000 unique rows. The identifier heading is a compatibility field; `--feature-unit probe` preserves probe identity. Values must be finite, already-normalized log2 expression from one platform. No missing values, re-normalization or probe aggregation.

Samples: exactly `sample_id`, `condition`, `subject_id` plus the one named categorical adjustment if used. Each subject occurs once and each condition has at least two declared independent subjects. Metadata is reordered to matrix columns. Rank-deficient/confounded or saturated designs fail. Paired subjects, continuous covariates, interactions and mixed models are unsupported.

```text
python3 scripts/run_microarray_de.py --expression expression.tsv --metadata samples.tsv   --output fit --assay microarray --scale log2-normalized --feature-unit probe   --taxon 9606 --namespace DECLARED_PROBE_NAMESPACE --platform DECLARED_PLATFORM   --normalization-provenance "Actual producer method and scale evidence"   --numerator treated --denominator control --alpha 0.05   --independent-samples-declared --rscript Rscript
```

If justified, add `--covariate batch` and that column. Values above are placeholders, not inferred facts. A suitable trusted R 4.4.1 / limma 3.60.6 environment must already exist; no installation or network is performed.

Method: fixed `lmFit` and `eBayes(trend=FALSE, robust=FALSE)`, condition coefficient after optional categorical adjustment; BH over all supplied features and pointwise 95% confidence intervals. Model runtime is bounded to 120 seconds. `baseMean` means mean log2 expression, not mean count; `stat` means moderated t, not a DESeq2 Wald statistic.

Outputs: `de.json`, `results.tsv`, unadjusted `pca.tsv` and `correlations.tsv`. PCA centers features without scaling them, uses all input features and does not remove a batch effect. Constant-sample correlations remain NA. Companion plotting may use an explicitly chosen variable-feature subset; its PCA must retain that different selection in its caption.

Gene-set handoff: current local mapping can read `de.json`. Namespace/taxon must match. Preserve mapping ambiguity by default; explicit exclusion removes all unresolved mappings and records losses. It never chooses one of several probes based on its observed p-value. If pre-fit gene summarization is needed, use a documented upstream policy and retain its provenance before this Skill.
