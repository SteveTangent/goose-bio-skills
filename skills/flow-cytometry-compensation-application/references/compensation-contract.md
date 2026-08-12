# Compensation contract

## Exact table convention

The event table is UTF-8 TSV with `event_id` first and one or more numeric
observed channels. The spillover table is UTF-8 TSV with `source_channel` first.
Its row labels and remaining headers must exactly equal the event channel list
and order.

For row-vector notation, `observed = true × spillover`; therefore the published
values are `observed × inverse(spillover)`. This package does not support a
transposed convention, estimated matrices, unmixed spectral data, or channel
aliasing.

## Bounded behavior

- at most 32 channels, 100,000 events, and 16 MiB per input;
- unique nonempty printable ASCII identifiers without whitespace; channel IDs
  `event_id` and `source_channel` are reserved;
- finite values in strict decimal syntax only: optional sign, decimal point,
  and base-10 exponent are supported, while whitespace, underscores, NaN, and
  infinity are rejected; each token is at most 128 characters;
- every diagonal spillover coefficient is exactly `1`; every off-diagonal
  coefficient has absolute value at most `1`;
- matrix pivots, inverse residual (at most `1e-8`), and infinity-norm condition
  number (at most `1e8`) must satisfy the fixed checks recorded in the report;
- compensated floats use Python's shortest round-trip representation (`0` for
  either signed zero); cross-platform byte identity is not claimed;
- input leaves and parents containing symlinks are refused, as are output
  symlink parents; both outputs use inode-bound, create-new publication and are
  rolled back together if either cannot be published.

Negative compensated values are valid descriptive output. Matrix suitability,
instrument setup, transforms, gating, and biological meaning remain researcher
decisions.
