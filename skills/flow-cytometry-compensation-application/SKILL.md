---
name: flow-cytometry-compensation-application
description: "Apply a supplied spillover matrix to a compatible cytometry event TSV. Exclude estimating spillover, raw FCS parsing, gating and clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Flow Cytometry Compensation Application

`Preview + reviewed`; the bounded deterministic helper self-test passed. Formal
agent runtime, representative cytometry data, scientific benchmarking, and
expert review were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use to apply one explicitly supplied square spillover matrix to matching numeric channels in an already extracted local flow-cytometry event TSV, producing create-new compensated events and provenance. Exclude FCS parsing, estimating or choosing compensation, transformations, gating, cell labels, batch correction, QC decisions, and biological or clinical interpretation.

## Owns

Apply one exact, invertible spillover matrix to one extracted event table. The
helper computes `compensated = observed × inverse(spillover)` and does not infer
whether the matrix is scientifically appropriate.

## Inputs

- event TSV: first column exactly `event_id`, followed by unique numeric channel
  names;
- spillover TSV: first column exactly `source_channel`; its remaining headers
  are observed channels, its row labels are source channels, and both channel
  lists must exactly match the event channels in the same order;
- two new output paths: compensated TSV and JSON provenance report.

The matrix convention is exact: entry `(i,j)` is the contribution of true
source channel `i` to observed channel `j`. Ask only if that convention or the
event-channel identity is unresolved; recommend exporting the producer-approved
matrix without transposing or relabeling it.

## Run

```text
python3 scripts/apply_compensation.py \
  --events extracted-events.tsv --spillover spillover.tsv \
  --output-events compensated-events.tsv --output-report compensation.json
```

Explicit readable local regular-file paths are accepted. Input leaves and
parent directories containing symlinks are refused. Output parents must already
exist without symlink components; both outputs are create-new and never replaced.

## Output contract

`completed` creates a TSV with the same event IDs and channel order plus a JSON
report binding both input hashes and the compensated-output hash, dimensions,
matrix convention, inverse
residual, condition diagnostic, and numeric limits. Numeric fields use strict
finite decimal syntax. The spillover matrix must have an exact unit diagonal,
bounded off-diagonal coefficients, and pass the recorded condition/residual
ceilings. Invalid tables, duplicate/reserved/mismatched channels,
singular/unstable matrices, symlinked paths, unsafe output leaves, and existing
outputs fail closed without claiming completion.

Event and channel identifiers are bounded printable ASCII tokens without any
whitespace.

Compensated values may be negative; the helper preserves them because clipping
or transforming would be a separate scientific decision.

## Guardrails

- Never estimate, transpose, repair, normalize, or choose a spillover matrix.
- Never parse FCS, transform intensities, gate, label cells, remove events, or
  interpret negative values.
- Never mutate inputs, follow symlinks, overwrite outputs, use the network, or
  invoke a subprocess.
- Require researcher review of matrix provenance, channel identities, instrument
  context, transformations, downstream gating, and interpretation.
