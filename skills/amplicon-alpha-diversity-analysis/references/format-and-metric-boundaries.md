# Format and metric boundaries

## Input contract

Use a UTF-8 TSV in exact feature-rows-by-sample-columns orientation:

```text
feature_id\tsample-a\tsample-b
feature-1\t10\t0
feature-2\t5\t8
```

Feature and sample IDs must be unique and nonempty. Every count must use ASCII
decimal digits only and be at least zero. Missing, signed, fractional,
exponential, normalized, relative-abundance, or negative values are rejected.
The helper does not read BIOM/QZA or infer a transposed table.

## Metric contract

For a sample with counts `x_i` and positive total `N`:

- observed features: count of features where `x_i > 0`;
- Shannon: `-sum(p_i * ln(p_i))` over positive counts, where `p_i=x_i/N`;
- Simpson diversity: `1 - sum(p_i^2)` over positive counts.

The logarithm is natural. No bias correction, confidence interval, Hill-number
conversion, rarefaction, extrapolation, or evenness is computed. For total
depth zero, all three metrics are `not-estimable`; reporting observed richness
as zero would conflate absence of observations with a biologically empty
community.

## Interpretation boundary

These values describe the supplied table only. Sequencing depth, feature
construction, filtering, primer choice, library preparation, contamination,
and study design can affect them. The helper does not establish adequate depth
or make samples comparable and must not be used for group testing, differential
abundance, taxonomy, pathogen detection, or biological/clinical conclusions.

## Runtime boundary

The helper reads at most 16 MiB, 50,000 features, 2,000 samples, and 2,000,000
cells. Counts and each sample total may not exceed `9007199254740991`, keeping
the integer totals exactly representable for deterministic ratio calculation.
It creates exactly one new JSON file below the current working directory and
performs no network or subprocess operations. Windows publication and symlink
behavior remain unverified.
