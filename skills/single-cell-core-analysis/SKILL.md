---
name: single-cell-core-analysis
description: "A user has a small validated single-cell count object and needs normalization, feature selection, PCA, neighborhood graph, embedding or clustering. Exclude: object conversion or QC ownership; batch integration; automatic cell-type annotation; trajectory, velocity or condition-level differential testing."
license: Apache-2.0
metadata:
  version: "0.4.0"
---

# Single-cell Core Analysis

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce a reproducible exploratory embedding and clustering baseline from an explicitly validated single-cell object. Exclusions are declared in the trigger above.

## Inputs

- validated single-cell count object
- QC decisions and preserved raw counts
- assay, modality and exploratory objective

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **single-cell-assay.** Which assay should drive core single-cell preprocessing? Recommended: Use the validated assay handed off by object I/O and QC.
2. **single-cell-objective.** Which exploratory objective should determine normalization and feature selection? Recommended: Use a small assay-appropriate baseline and preserve authoritative counts.

## Workflow

1. Verify the object/QC handoff and preserve authoritative counts.
2. Choose an assay-appropriate bounded preprocessing baseline.
3. Record stochastic seeds and construct feature, PCA, graph and clustering outputs.
4. Report sensitivity to key settings and keep interpretation exploratory.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- processed object with preserved provenance
- normalization, feature, PCA, graph and clustering diagnostics
- descriptive markers labelled as exploratory when requested

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Require a validated object, authoritative counts layer, and explicit QC handoff before analysis
- Fix normalization, HVG method, PCA dimensions, neighbor backend, seed, UMAP, clustering algorithm, and resolution
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
