---
name: protein-structure-retrieval-and-comparison
description: "Retrieve or compare existing protein structures with explicit identifiers and comparison assumptions. Exclude de novo prediction, molecular dynamics and functional or affinity claims."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Protein Structure Retrieval and Comparison

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user needs to retrieve known structures or compare two existing protein structures or models. Exclude: predicting a new structure; docking or molecular dynamics; equating prediction confidence with experimental resolution; structural database search beyond pairwise comparison.

## Owns

Resolve structure identity, assembly, chain and confidence before producing an auditable structural comparison. Apply the detailed scope below.

## Inputs

- protein accession or structure identifiers
- chain and assembly intent
- comparison region and metric
- local PDB or mmCIF structure files with hashes

## Intake

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

Decision order:

1. **structure-assembly.** Which assembly? Recommended: prefer the relevant experimental assembly and separate predictions.
2. **structure-chain.** Which chain? Recommended: resolve an exact mapping across entries.
3. **structure-range.** Which residues? Recommended: use the shared resolved region and report missing residues.

## Public network execution

An explicit public retrieval authorizes bounded anonymous metadata and file
downloads from `rcsb-pdb` or `alphafold-db`. Confirm sensitive data, non-default
hosts, or unrequested bulk. On failure, use a hash-bound local structure or
return `needs-tool`/partial. Record accession, model version, assembly or chain,
provider, access time, hashes, and network use.

## Workflow

1. Resolve protein, structure, assembly and chain identifiers.
2. Retrieve through a pinned snapshot or the bounded public providers above.
3. Separate experimental quality from prediction confidence.
4. Compare declared regions and report mapping, metric and missing residues.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- retrieved structure artifacts or references
- experimental and prediction confidence metadata
- alignment mapping and comparison metrics with caveats

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Retrieval does not
make a prediction experimental evidence or prove the selected assembly.

## Guardrails

- Record accession, entry or model version, experimental or predicted status, assembly, chain, residue mapping, retrieval date, and file hash
- Separate experimental resolution from AlphaFold pLDDT and PAE confidence
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
