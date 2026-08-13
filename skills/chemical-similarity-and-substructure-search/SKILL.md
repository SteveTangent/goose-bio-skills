---
name: chemical-similarity-and-substructure-search
description: "A user has standardized molecules and needs fingerprint similarity or SMARTS-like substructure retrieval. Exclude standardization, biological or mechanism inference, docking, and QSAR."
license: Apache-2.0
metadata:
  version: "0.8.0"
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

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

Decision order:

1. **search-mode.** Similarity or exact substructure? Recommended: choose one before selecting representation.
2. **fingerprint-representation.** Which fingerprint? Recommended: use a domain-matched versioned fingerprint.
3. **similarity-metric.** Which metric? Recommended: match it to the fingerprint and objective.
4. **similarity-threshold.** Which calibrated threshold should define a reported similarity match? Recommended: Use a fixture-calibrated threshold and never present it as biological equivalence.

## Public network execution

An explicit public structure search authorizes bounded anonymous reads from
`pubchem-pug-rest` or the user-selected `chembl-rest`. Confirm proprietary or
unpublished structures, non-default hosts, and unrequested bulk. On failure,
return `needs-tool` or partial. Record provider, access time, standardized-query
digest, pagination, hashes, and network use.

## Workflow

1. Verify query and library share the same standardization contract.
2. Declare fingerprint, metric, threshold or substructure semantics.
3. Run a bounded deterministic local or public-provider search.
4. Report matches and explain that structural similarity is not functional equivalence.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- ranked or matched structures
- fingerprint, metric and threshold record
- invalid-query and standardization-compatibility findings

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). A live hit does not
make structural similarity biological equivalence.

## Guardrails

- Require an explicitly standardized representation and preserve the original molecule record
- Record fingerprint type and version, radius, bit length, chirality policy, similarity metric, threshold, and reference-library release
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
