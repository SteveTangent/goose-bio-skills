---
name: flow-cytometry-arcsinh-transformation
description: "Use to apply explicit positive per-channel arcsinh cofactors to selected numeric channels in one already extracted local flow-cytometry event TSV, producing create-new transformed events and provenance. Exclude FCS parsing, compensation, choosing or estimating cofactors, logicle or biexponential transforms, gating, cell labels, QC decisions, and biological or clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.9.0"
---

# Flow Cytometry Arcsinh Transformation

`Preview + reviewed`; the bounded deterministic helper self-test passed. Formal
agent runtime, representative cytometry data, scientific benchmarking, and
expert review were not performed.

## Owns

Apply `asinh(value / cofactor)` to the explicitly selected channels of one
already extracted event table. Preserve event IDs, row order, channel order,
negative values, and the exact tokens of unselected numeric channels.

## Inputs

- event TSV: first column exactly `event_id`, followed by unique numeric channel
  names;
- cofactor TSV: exactly `channel` and `cofactor`, with one or more unique event
  channels and a strictly positive finite cofactor for each;
- two new output paths: transformed TSV and JSON provenance report.

Ask only when the cofactor or selected-channel identity is unresolved. Recommend
using predeclared, instrument/workflow-approved cofactors; never estimate them
from the observed values.

## Run

```text
python3 scripts/apply_arcsinh.py \
  --events extracted-events.tsv --cofactors cofactors.tsv \
  --output-events transformed-events.tsv --output-report arcsinh.json
```

Explicit readable local regular-file paths are accepted. Input leaves and
parent directories containing symlinks are refused. Output parents must already
exist without symlink components; both outputs are create-new and never replaced.

## Output contract

`completed` creates a TSV with the same event IDs and channel order plus a JSON
report binding input hashes, selected channels and exact cofactors, output hash,
dimensions, formula, and numeric limits. Selected channels use Python's shortest
round-trip float representation, with signed zero normalized to `0`; unselected
channel tokens remain byte-for-byte equal within their TSV cells.

Invalid tables, duplicate/reserved/unknown channels, nonpositive or nonfinite
cofactors, numeric overflow or underflow, symlinked paths, unsafe output leaves,
and existing outputs fail closed without claiming completion. Pair publication
uses checked exception rollback and is not crash-atomic between both links.
Same-directory hostile-writer races and Windows publication behavior remain
outside the verified boundary.

## Guardrails

- Never choose, estimate, optimize, or silently replace a cofactor.
- Never parse FCS, compensate, apply another transform, gate, label cells,
  remove events, or interpret transformed values.
- Never mutate inputs, follow symlinks, overwrite outputs, use the network, or
  invoke a subprocess.
- Require researcher review of cofactor provenance, channel identities,
  instrument context, downstream gating, and interpretation.
