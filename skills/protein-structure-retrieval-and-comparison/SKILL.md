---
name: protein-structure-retrieval-and-comparison
description: "A user needs to retrieve known structures or compare two existing protein structures or models. Exclude: predicting a new structure; docking or molecular dynamics; equating prediction confidence with experimental resolution; structural database search beyond pairwise comparison."
---

# Protein Structure Retrieval and Comparison

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Resolve structure identity, assembly, chain and confidence before producing an auditable structural comparison. Exclusions are declared in the trigger above.

## Inputs

- protein accession or structure identifiers
- chain and assembly intent
- comparison region and metric
- local PDB or mmCIF structure files with hashes

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **structure-assembly.** Which biological assembly should be compared? Recommended: Prefer the relevant experimental biological assembly when available and report predicted alternatives separately.
2. **structure-chain.** Which chain should be compared? Recommended: Resolve one exact chain mapping rather than assuming chain labels are equivalent across entries.
3. **structure-range.** Which residue range should be compared? Recommended: Use the shared resolved region and report missing or unmapped residues.

## Workflow

1. Resolve protein, structure, assembly and chain identifiers.
2. Retrieve through a pinned snapshot or disclosed read-only adapter.
3. Separate experimental quality from prediction confidence.
4. Compare declared regions and report mapping, metric and missing residues.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- retrieved structure artifacts or references
- experimental and prediction confidence metadata
- alignment mapping and comparison metrics with caveats

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Record accession, entry or model version, experimental or predicted status, assembly, chain, residue mapping, retrieval date, and file hash
- Separate experimental resolution from AlphaFold pLDDT and PAE confidence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
