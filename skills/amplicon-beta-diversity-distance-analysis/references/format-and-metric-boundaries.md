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

For two positive-depth samples with feature counts `x_i` and `y_i`:

- Bray-Curtis dissimilarity has numerator `sum(abs(x_i-y_i))` and denominator
  `sum(x_i+y_i)`;
- presence/absence Jaccard distance has numerator `union-intersection` and
  denominator `union`, using `count > 0` as presence.

The floating `value` is the numerator divided by the denominator. The exact
integer numerator and denominator in the report are authoritative. If either
sample has total depth zero, both metrics are `not-estimable` with reason
`zero-depth-sample`; this helper does not report a potentially misleading
maximal distance from a sample with no observations.

Sample IDs are sorted by Python's Unicode code-point order. Results contain
each unordered pair exactly once in upper-triangle order. The helper does not
transform counts or compute abundance-weighted Jaccard, UniFrac, Aitchison,
ordination, confidence intervals, or p-values.

## Interpretation boundary

Distances describe the supplied table only. Sequencing depth, feature
construction, filtering, primer choice, library preparation, contamination,
and study design can affect them. The helper does not establish adequate depth
or make samples suitable for group testing and must not be used for ordination,
PERMANOVA or other group comparison, differential abundance, taxonomy,
pathogen detection, or biological/clinical conclusions.

## Runtime boundary

The helper reads at most 16 MiB, 50,000 features, 2,000 samples, 2,000,000
cells, 20,000 sample pairs, and 20,000,000 pair-feature comparisons. Counts and
each sample total may not exceed `9007199254740991`. It creates exactly one new
JSON file below the current working directory and performs no network or
subprocess operations. Exception rollback is tested, but publication is not
crash-atomic: a process crash can leave a hidden staged file, and a
same-directory malicious writer could race adjacent identity checks. Windows
publication and symlink behavior remain unverified.
