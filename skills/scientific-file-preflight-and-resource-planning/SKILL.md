---
name: scientific-file-preflight-and-resource-planning
description: "Use for a bounded, read-only preflight of explicitly named local scientific files before a workflow starts. Estimate container clues, index presence, and conservative resource floors. Exclude full validation, recursion, decompression, repair, conversion, execution, and biological interpretation."
license: Apache-2.0
metadata:
  version: "0.4.0"
---

# Scientific File Preflight and Resource Planning

`Preview + reviewed`; the helper self-test passed. Large-file calibration,
scientific benchmarking, and expert review were not performed.

## Scope and inputs

Inspect metadata and a capped header from explicit local regular files. Identify
obvious blockers and provide heuristic planning floors for `metadata-only`,
`sequential-read`, `indexed-analysis`, or `sort-or-rewrite`; do not claim
operational readiness, format validity, or scientific validity.

Require:

- one or more explicit file paths;
- the intended operation class;
- optional disk and memory budgets in bytes;
- a new JSON output path in an existing directory.

An explicit request authorizes these bounded reads and the new report. If the
operation class is missing, ask one question and recommend naming the actual
downstream operation; do not ask for a second execution confirmation.

## Run

```text
python3 scripts/preflight_files.py \
  --input FILE [--input FILE ...] \
  --operation metadata-only|sequential-read|indexed-analysis|sort-or-rewrite \
  --output NEW_REPORT.json \
  [--probe-bytes 65536] [--disk-budget-bytes N] [--memory-budget-bytes N]
```

The Python 3.10+ helper accepts at most 256 files, 1 MiB per probe, and
64 MiB total. It refuses leaf symlinks, directories, special files, parent
traversal, changed inputs, and existing outputs. It creates no directories.

## Result

`completed` requires every input to pass and one create-new report to publish.
The report records file metadata, inspected bytes, whether the probe covered the
whole file, suffix and magic clues, probe digests, companion-index presence,
warnings, planning floors, budgets, versions, and assumptions.

Missing choices are `needs-decision`; unsupported work is `needs-tool`; unsafe
inputs are `invalid-input`. No report is published after an input failure.

## Boundaries

- Never recurse, decompress, run a subprocess, use the network, mutate input, create an index, or overwrite output.
- A full-file probe of a small file is labeled explicitly; it is not presented as a separately requested whole-file hash.
- Container clues and companion presence do not establish structural or scientific validity.
- Resource values are conservative triage floors, not measured runtime predictions.
- Route format validation to `bioinformatics-format-and-identifier-validation`, file operations to their owning Skills, and completed-run provenance to `environment-and-provenance-capture`.

See [runtime boundaries](references/runtime-boundaries.md) for tested and skipped behavior.
