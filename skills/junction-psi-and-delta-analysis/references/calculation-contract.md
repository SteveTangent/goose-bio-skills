# Calculation contract

## Accepted tables

Use UTF-8, tab-delimited, uncompressed regular files with one header row and no
blank rows. Counts must have exact columns `event_id`, `sample_id`,
`inclusion_count`, and `exclusion_count`. Groups must have exact columns
`sample_id` and `group`. IDs and labels must be nonempty, unique where
applicable, and free of leading or trailing whitespace.

Every event must contain exactly one row for every sample in the groups file.
The groups file must contain only the declared group-A and group-B labels, with
at least one sample in each. Counts are canonical nonnegative base-10 integers
no larger than 2^63 - 1.

## Calculations

For one event and sample:

```text
coverage = inclusion_count + exclusion_count
PSI = inclusion_count / coverage
```

Report PSI only when `coverage >= minimum coverage`; otherwise report it as
`not-estimable` with reason `coverage-below-minimum`. For each group, compute the
unweighted arithmetic mean of its estimable sample PSI values. Do not impute or
weight low-coverage samples. Compute the event delta only when both group means
are estimable:

```text
delta_psi = mean_psi(group B) - mean_psi(group A)
```

The JSON contains exact rational strings and decimal values rounded to 12
decimal places. Treat the rational string as the exact result.

## Failure and interpretation boundaries

Reject malformed schemas, duplicate event-sample pairs, incomplete or extra
sample joins, groups outside the two declared labels, invalid integers,
oversized inputs, changed-during-read inputs, leaf symlinks, missing output
parents, and existing outputs. Data-supported not-estimable values are valid
descriptive results and remain in a completed report.

The calculation assumes the upstream inclusion and exclusion counts are
compatible and event definitions are biologically meaningful. It does not
validate junction discovery, mapping, strandedness, isoform models, replicate
independence, or study design. Review those upstream facts before interpreting
PSI or delta PSI.
