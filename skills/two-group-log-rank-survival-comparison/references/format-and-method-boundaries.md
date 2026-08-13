# Format and method boundaries

## Input contract

Use UTF-8 TSV with the exact header:

```text
subject_id\ttime\tevent\tgroup
```

- `subject_id`: unique, nonempty identifier.
- `time`: exact finite decimal elapsed time greater than or equal to zero, in
  one declared unit and from one declared origin. Strict decimal syntax allows
  an optional sign, decimal point, and base-10 exponent. Whitespace, NaN,
  infinity, and hexadecimal forms are rejected. The adjusted base-10 exponent
  must remain between `-128` and `128`.
- `event`: exact `1` for the prespecified event or exact `0` for right
  censoring.
- `group`: one of exactly two nonempty, prespecified cohort labels. Labels are
  sorted lexicographically for deterministic group-A/group-B output; this order
  is not a scientific ranking.

Missing values, weights, delayed entry, multiple rows per subject, recurrent or
competing events, interval censoring, time-varying values, and more than two
groups are outside the contract. Prepare a fit-for-purpose subject table
upstream.

## Mantel-Cox contract

At each distinct time containing at least one event, count subjects at risk
immediately before that time. Same-time events occur before same-time censors
leave the risk set. For group A at one event time:

```text
n = nA + nB
d = dA + dB
EA = d * nA / n
VA = nA * nB * d * (n - d) / (n^2 * (n - 1))
```

Use `VA=0` when `n <= 1`. Sum observed `dA`, expected `EA`, and variance `VA`
over event times. When total variance is positive, report
`chi_square = (OA - EA)^2 / V`, one degree of freedom, and the unadjusted
two-sided p-value `erfc(sqrt(chi_square / 2))`. When total variance is zero,
report structured `not-estimable` status and null statistic/p-value fields.
When positive variance yields a finite chi-square but the platform p-value
underflows to zero, retain the statistic and report `p_value_status=underflow`
with a null p-value rather than a false exact zero.

Risk-set expectations, observed-minus-expected values, variances, and the
chi-square statistic are accumulated as exact rational numbers. The reported
p-value uses the platform C math library; its last binary floating-point digit
is not a cross-platform guarantee, and extreme finite tails may be reported as
structured underflow.

No Kaplan-Meier estimate, confidence interval, hazard ratio, multiplicity
correction, significance threshold, or significance decision is computed.

## Runtime boundaries

The helper reads at most 16 MiB and 100,000 subjects. It uses only the Python
standard library, performs no network or subprocess operations, and creates
exactly one new JSON file below the current working directory. Input and output
symlinks, missing output parents, directory escape, and replacement of existing
paths are refused. Publication is create-new with checked exception rollback,
not crash-atomic. Same-directory hostile writers and Windows publication and
symlink behavior remain unverified.
