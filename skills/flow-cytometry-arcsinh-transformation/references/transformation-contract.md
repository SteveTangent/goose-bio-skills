# Arcsinh transformation contract

## Exact tables

The event table is UTF-8 TSV with `event_id` first and one or more numeric
channels. The cofactor table is UTF-8 TSV with exactly `channel` and `cofactor`.
Its rows select a nonempty subset of event channels. Identifiers are unique,
nonempty printable ASCII without whitespace; `event_id` and `channel` are
reserved channel names.

All numeric input uses strict finite decimal syntax: optional sign, decimal
point, and base-10 exponent are supported; whitespace, underscores, NaN, and
infinity are rejected. Each token is at most 128 characters. Cofactors must be
strictly greater than zero.

## Fixed calculation

For every selected channel, calculate `asinh(value / cofactor)`. Negative values
are retained; either signed zero becomes `0`. Selected values use Python's
shortest round-trip float representation. Unselected numeric cell tokens are
copied exactly. This package does not estimate a cofactor or infer a scale.

## Bounded behavior

- at most 64 channels, 100,000 events, 64 selected channels, and 16 MiB per
  input;
- a selected division that overflows or a nonzero input/cofactor that underflows
  the supported float calculation fails closed;
- input leaves and parents containing symlinks are refused, as are output
  symlink parents;
- both outputs use inode-checked create-new publication and checked exception
  rollback; the two hard links are not crash-atomic. Same-directory hostile
  writer races and Windows publication and symlink behavior are unverified. A
  rare pre-identity staging failure may leave a hidden mode-0600 temporary file.

FCS parsing, compensation, other transformations, cofactor choice, gating,
labeling, QC, and biological or clinical interpretation remain outside scope.
