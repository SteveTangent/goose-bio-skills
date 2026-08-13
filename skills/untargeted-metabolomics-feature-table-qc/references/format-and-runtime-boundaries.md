# Format and runtime boundaries

This reference defines `untargeted-metabolomics-feature-table-qc` version
`0.9.0`. The bundled helper is an original, dependency-free implementation.

## Exact input contract

- Accept one feature-by-sample UTF-8 TSV with exact leading headers
  `feature_id`, `mz`, and `retention_time_seconds`. Require unique nonempty
  feature and sample IDs, finite positive m/z, and finite nonnegative retention
  time in seconds.
- Accept one metadata UTF-8 TSV with exact headers `sample_id`, `sample_type`,
  `batch`, and `injection_order`. Require unique sample IDs and sample types
  `study`, `pooled_qc`, or `blank`. Batch and injection order may be blank so
  completeness can be reported; a present injection order is a positive
  integer.
- Require feature-table and metadata sample-ID sets to match exactly.
- Require every intensity cell to be either a finite nonnegative number or the
  caller-declared exact nonnumeric missing token. Record the intensity semantic
  as `raw-peak-area`, `raw-peak-height`, or
  `processed-nonnegative-abundance`.
- Under zero semantics `observed`, zero is a detected numeric value and remains
  in descriptive moments. Under `missing`, zero remains in the source but is
  counted and excluded like a missing cell. The helper never infers semantics.

## Descriptive calculations

For each sample, report detected, missing-token, zero-as-missing, and total
missing feature counts. For each feature, calculate pooled-QC RSD as the sample
standard deviation divided by the arithmetic mean times 100 after applying the
declared missing semantics. Report `not-estimable` when no pooled-QC samples
exist, fewer than two usable values remain, the usable mean is zero, or finite
inputs cannot produce finite mean, standard-deviation, or RSD arithmetic
(`numeric-range-overflow`).

Calculate the per-feature blank-to-study ratio from arithmetic means after the
same missing semantics. Report `not-estimable` when either sample type is
absent, either group has no usable values, or the study mean is zero. These
summaries also report `numeric-range-overflow` when finite inputs cannot
produce a finite ratio. They do not establish analytical precision, contamination, carryover,
detection limits, or fitness for downstream analysis.

## Safety, scale, and exclusions

Each input is a stable regular non-symlink file no larger than 16 MiB. The
helper accepts at most 50,000 features, 2,000 samples, 10,000 metadata rows,
and 2,000,000 intensity cells. It writes one create-exclusive JSON artifact
below the current directory, requires existing non-symlink parents, and uses
no network or subprocess. Unsupported scale returns invalid input and creates
no report.

Exclude raw or converted MS files, peak picking, feature alignment, drift or
batch correction, filtering, normalization, imputation, compound annotation,
identification confidence, differential or pathway analysis, contamination or
carryover decisions, and biological or clinical interpretation. The self-test
covers a five-feature by nine-sample synthetic table, exact summaries,
nonfinite and negative inputs, duplicate and join failures, orientation,
determinism, symlink refusal, output-root boundaries, and no-overwrite
publication. It is not an agent evaluation, representative-data benchmark, or
expert review.
