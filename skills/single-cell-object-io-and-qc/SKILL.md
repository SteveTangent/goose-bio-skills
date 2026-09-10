---
name: single-cell-object-io-and-qc
description: "Inspect single-cell objects, sample and feature metadata, and QC summaries; plan compatible conversion. Exclude automatic filtering, normalization, integration and cell-type annotation."
license: Apache-2.0
metadata:
  version: "0.11.0"
---

# Single-cell Object I/O and QC

`Preview + reviewed`; small local helper checks are separate from agent, scientific, expert and clinical validation.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user needs to inspect, load, or quality-check a supported small single-cell object, or plan a conversion through a declared adapter. Exclude: silent make-unique, filtering or doublet removal; normalization and clustering; condition differential expression; cross-ecosystem conversion without a declared compatible converter.

## Owns

Inspect, load, and quality-check supported single-cell objects without silent mutation; cross-ecosystem conversion requires a declared converter. Apply the detailed scope below.

## Inputs

- small AnnData, Zarr, 10X, Seurat or SingleCellExperiment-like object
- assay, layer and raw-count intent
- sample and modality context

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **authoritative-count-source.** Which assay or layer is the authoritative count source for QC? Recommended: Inspect all candidates and never copy the current matrix into a counts slot by default.

## Workflow

1. Inspect axes, identifiers, assays, layers, sparsity and backed state.
2. Resolve the intended raw-count source instead of guessing from object names.
3. Calculate explicit QC metrics stratified by relevant sample groups.
4. For conversion, declare a compatible converter and loss contract; otherwise return dry-run or needs-tool.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- object, assay, layer, axis and sparsity inventory
- per-cell and per-feature QC metrics
- proposed thresholds and conversion-loss manifest

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Record the object and file version, axes, assays, layers, authoritative counts source, sparse or backed state, and duplicate-ID policy
- Inventory conversion losses for assays, layers, categories, graphs, sparse types, and provenance
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority

## Small local execution adapter (0.11.0)

Inspect and explicitly filter a small RNA h5ad with authoritative counts and biological sample metadata. Use [the local adapter](references/local-adapter.md) for exact inputs, flags, outputs and limits. Broader guidance above remains available; only this declared adapter has small execution evidence. No undocumented route is silently substituted.
