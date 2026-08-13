---
name: fcs-file-io-and-metadata-qc
description: "Use for bounded local inspection of Flow Cytometry Standard files and metadata. Check FCS structure, datasets, event and channel counts, channel labels and scaling keywords, time, and spillover declarations. Exclude compensation, transformation, gating, clustering, workspace import, rewriting, and clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.8.0"
---

# FCS File I/O and Metadata QC

`Preview + reviewed`; FlowIO execution and scientific benchmarking were not performed.

## Scope and inputs

Inspect named local FCS files without changing them. Default to metadata only.
Require the files, objective, and any event-statistics bound. Inspect safe facts
first; ask one question only when a result-changing choice remains:

1. **fcs-dataset-scope.** Which file and dataset governs the report? Recommended: report bounded datasets separately; never merge implicitly.
2. **fcs-event-statistics.** What event or memory bound applies? Recommended: remain metadata-only unless statistics are necessary.

Ask with the recommendation, then wait before continuing.

An explicit local request authorizes bounded reads and one new report, not
recursive discovery, event export, or input mutation.

## Workflow

1. Preflight regular, non-symlink inputs and size; delegate uncertain resources to `scientific-file-preflight-and-resource-planning`.
2. Use a reviewed FlowIO adapter for FCS 2.0/3.0/3.1 metadata first. Do not write an ad hoc parser or hide offset errors.
3. Report datasets and offsets, version, DATA type, event/parameter counts, byte order, and required keys. Flag impossible counts, duplicate labels, and suspicious chains.
4. Preserve parameter order and report `$PnN`, `$PnS`, `$PnE`, `$PnG`, and `$PnR`. Report declared date, instrument, time, spillover, plate, and well state; omit unrestricted TEXT/ANALYSIS metadata by default.
5. Only within an explicit bound, calculate simple finite-value summaries. Label encoded versus scaled values and state that they remain uncompensated and ungated.

## Result and boundaries

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. Bind file identity, dataset scope, adapter/version, counts,
channel map, findings, warnings, event semantics, skipped checks, and digest.

- Do not infer populations, marker positivity, or sample quality from metadata.
- Do not compensate, transform, gate, cluster, concatenate, export events, import workspaces, or rewrite FCS.
- Do not treat a declared spillover matrix as proof that compensation was applied correctly.
- Do not upload files or use network services. Never overwrite input or output files.
- If FlowIO is unavailable or memory exceeds the bound, return `needs-tool` or `partial`; skipped is not passed.

See [runtime boundaries](references/runtime-boundaries.md) for the reviewed
adapter and unverified behavior.
