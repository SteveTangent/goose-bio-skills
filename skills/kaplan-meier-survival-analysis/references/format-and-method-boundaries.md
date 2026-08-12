# Format and method boundaries

## Input contract

Use UTF-8 TSV with exactly one of these headers:

```text
subject_id\ttime\tevent
subject_id\ttime\tevent\tgroup
```

- `subject_id`: unique, nonempty identifier.
- `time`: exact finite decimal elapsed time greater than or equal to zero, in
  one declared unit and from one declared origin. Strict decimal syntax allows
  an optional sign, decimal point, and base-10 exponent; whitespace, NaN,
  infinity, and hexadecimal forms are rejected. The adjusted base-10 exponent
  must remain between `-128` and `128` so exact output stays bounded.
- `event`: exact `1` for the prespecified event or exact `0` for right
  censoring.
- `group`: optional nonempty prespecified cohort label used only to produce
  separate descriptive curves.

Missing values, left or interval censoring, delayed entry, multiple rows per
subject, recurrent events, competing events, weights, and time-varying values
are outside this contract. Export a fit-for-purpose subject table upstream.

## Kaplan-Meier contract

At each distinct observed time, `n_at_risk` is the count just before that time.
The product-limit step is `S(t) = S(t-) * (1 - d/n)`, where `d` is the event
count and `n` is the risk-set count. Subjects censored at the same time are
removed after the event step. Rows include event-only and censor-only times.

The median is the earliest observed time at which the estimate is at most
`0.5`. If the curve never reaches `0.5`, the report returns `not-reached` and a
null time. No confidence interval is computed.

The helper groups and orders times with exact base-10 decimal arithmetic.
Integral output times are JSON integers; non-integral output times are
canonical decimal strings. Consumers must accept both representations and
must not parse decimal strings through a binary float before ordering them.

No log-rank, Cox, or other inferential comparison is performed. Group curves
remain descriptive and must not be interpreted as evidence of a difference.

## Runtime boundaries

The helper reads at most 16 MiB, 100,000 subjects, and 20 groups. It uses only
the Python standard library, performs no network or subprocess operations, and
creates exactly one new JSON file below the current working directory. Input
and output symlinks, missing output parents, directory escape, and replacement
of existing paths are refused. Windows publication and symlink behavior remain
unverified.
