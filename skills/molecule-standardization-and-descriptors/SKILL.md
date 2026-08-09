---
name: molecule-standardization-and-descriptors
description: "A user needs to clean SMILES/SDF records, normalize structures or compute declared molecular descriptors. Exclude: similarity search; QSAR training; claiming biological mechanism from descriptors."
license: Apache-2.0
metadata:
  version: "0.2.1"
---

# Molecule Standardization and Descriptors

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Create traceable standardized molecular representations and descriptors without erasing the original records. Exclusions are declared in the trigger above.

## Inputs

- SMILES, SDF or equivalent records
- standardization policy
- descriptor list and software version

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **fragment-policy.** Which parent-fragment policy should handle salts and mixtures? Recommended: Preserve the original and select a declared parent without silently discarding components.
2. **charge-policy.** Which charge or protonation policy should standardization use? Recommended: Freeze one policy matched to the downstream use and record every change.
3. **tautomer-policy.** Which tautomer policy should standardization use? Recommended: Use one versioned deterministic policy and retain the original representation.
4. **stereochemistry-policy.** How should specified and unspecified stereochemistry be preserved? Recommended: Preserve specified stereochemistry and keep unspecified centers explicitly unknown.

## Workflow

1. Parse structures and retain an immutable original representation.
2. Apply the declared fragment, charge, tautomer and stereochemistry policy.
3. Calculate versioned descriptors on the standardized form.
4. Report failed records, transformations and representation hashes.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- standardized structures linked to originals
- descriptor table
- reject, warning and transformation log

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Fix fragment, charge and protonation, tautomer, stereochemistry, aromaticity, and descriptor policies
- Preserve original molecule records and a complete transformation log
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
