# Bounded DESeq2 adapter

The original Python helper launches a fixed embedded R worker with `--vanilla`,
without a shell, downloads, installation or caller-provided R code. Rscript and
its package library must already be trusted and installed. The caller declares
the exact DESeq2 version; mismatch returns `needs-tool`. The smoke-tested stack
is R 4.6.1, DESeq2 1.52.0 and jsonlite 2.0.0. Other stacks remain unverified.

## Input and design

Use regular, uncompressed UTF-8 TSVs, each at most 8 MiB, inside the current
working directory. Counts start with `gene_id`, followed by 4–32 unique samples
and 20–30,000 unique genes. Values must be nonnegative raw integers within the
signed 32-bit range. Normalized values and transcript estimates are not accepted
by this adapter; use a separate reviewed import workflow for those inputs.

Metadata starts with `sample_id`, then `condition`, plus the one explicitly
named categorical covariate if used. No extra columns, missing samples, duplicate
IDs, unknown contrast levels or inferred recoding. Metadata is reordered to
match count columns. Each group requires at least two declared biological
replicates; a table alone cannot establish biological independence. Continuous
covariates, interactions and paired/repeated designs are outside this adapter.

The design must have full rank and positive residual degrees of freedom.
Declare minimum count and minimum number of samples before viewing results.
At least 20 genes and nonzero library sizes must remain. The helper uses DESeq2
median-ratio size factors and its Wald test for numerator minus denominator.
Declare dispersion fit, alpha, independent filtering and Cook's cutoff. An
automatic dispersion-fit change fails closed. Count replacement is disabled;
no fold-change shrinkage, alternate model or imputation is performed.

## Outputs and limits

One create-new JSON report contains input and worker hashes, declared settings,
R and package versions, effects, standard errors, Wald statistics, raw p-values,
BH-adjusted p-values, warnings, size factors, design rank, filtering counts,
missing significance counts, median dispersion and log-count sample distances.
Missing significance values remain null, never zero or significant. The sample
distance summary is a diagnostic aid, not batch correction or a QC approval.

The whole model must finish and pass output identity, dimension, scale and
finite-value checks before publication. Inputs are immutable; paths outside the
working directory, symlinks, parent traversal, existing outputs and missing
parents are refused. A 120-second model timeout returns a non-completed status.
These path checks assume a trusted local workspace, not a hostile concurrent
writer or untrusted replacement R executable. Host permissions remain binding.

A small public-data smoke check and deterministic contract checks establish
basic execution only. They do not validate other assays, arbitrary study
designs, biological findings, model superiority or clinical use. Researcher
review of QC, biological independence, confounding and interpretation remains
necessary. No full per-gene influence plots or shrinkage diagnostics are supplied.
