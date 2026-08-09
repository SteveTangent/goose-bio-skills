---
name: chemical-similarity-and-substructure-search
description: "A user has standardized query and reference molecules and needs fingerprint similarity or SMARTS-like substructure retrieval. Exclude: molecule standardization ownership; biological activity or mechanism inference; docking or QSAR."
license: Apache-2.0
metadata:
  version: "0.2.1"
---

# Chemical Similarity and Substructure Search

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Return reproducible matches with exact representation, fingerprint, metric, and threshold provenance.

## Inputs

- standardized query structures
- standardized reference library
- fingerprint or substructure definition
- similarity metric and threshold

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **search-mode.** Is the requested retrieval based on similarity or an exact substructure query? Recommended: Choose one search semantics before selecting a representation.
2. **fingerprint-representation.** Which fingerprint representation should encode similarity? Recommended: Use a domain-matched versioned fingerprint.
3. **similarity-metric.** Which similarity metric should score the selected fingerprint? Recommended: Use a metric compatible with the fingerprint and retrieval objective.
4. **similarity-threshold.** Which calibrated threshold should define a reported similarity match? Recommended: Use a fixture-calibrated threshold and never present it as biological equivalence.

## Workflow

1. Verify query and library share the same standardization contract.
2. Declare fingerprint, metric, threshold or substructure semantics.
3. Run a bounded deterministic search.
4. Report matches and explain that structural similarity is not functional equivalence.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- ranked or matched structures
- fingerprint, metric and threshold record
- invalid-query and standardization-compatibility findings

Record fingerprints, parameters, versions, warnings, and limitations. Never
fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Require an explicitly standardized representation and preserve the original molecule record
- Record fingerprint type and version, radius, bit length, chirality policy, similarity metric, threshold, and reference-library release
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
