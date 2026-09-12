# Local 2×2 adapter

Python >=3.10; numerical execution requires SciPy 1.17.1. No runtime installation.
Inputs at most 8 MiB; integer table total at most 100,000. No weights/fractions.

```text
python3 scripts/compare_2x2.py --self-test
python3 scripts/compare_2x2.py --table counts.tsv --numerator exposed --denominator control --event-label event --nonevent-label no-event --sampling-design cohort --independent --confidence-level 0.95 --output comparison-new
```

Input columns are exactly group/event/non_event. The helper orders the two rows
by explicitly supplied numerator/denominator. Event/non-event meanings are
explicit labels, not guesses from an arbitrary count table. Sampling design is
cohort, randomized, cross-sectional, case-control or unknown. Confidence level is
0.8–0.999 (default 0.95). Declared independence is not verified by aggregate counts.
Unknown design or absent independence blocks numerical inference. Paired, clustered
or repeated observations cannot be made independent by an --independent flag.

For rows [a,b] and [c,d], OR compares (a/b) / (c/d). The sample estimator is ad/bc;
the reported primary estimate is conditional MLE from the noncentral hypergeometric
model. Fisher's p-value is the two-sided probability-ordering version, not a
large-sample chi-square approximation or simply twice a one-sided result. The
conditional exact interval uses equal-tailed inversion. These two-sided conventions
can produce different boundary decisions. No significance label is assigned.

The JSON represents infinite estimates/bounds as the string infinity, finite
values as numbers, and keeps exact zero. A zero cell is supported; an empty entire
row or column yields needs-decision because the OR is not identifiable in this
path. Never apply automatic continuity correction. Group counts preserve observed
denominators, including in a case-control study, but population risk, risk ratio
and risk difference are not computed. Statistical outputs are exploratory research
support, not causal or clinical conclusions.

For more than one prespecified table, a separate multiple-testing plan is needed;
this helper does not silently screen a collection or choose the most favorable
orientation. Reversing either row or column direction inverts the OR and its
interval; reversing both leaves it unchanged. The two-sided p-value is invariant.
