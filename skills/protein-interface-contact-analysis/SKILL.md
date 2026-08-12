---
name: protein-interface-contact-analysis
description: "Use for bounded, offline residue-contact analysis between two explicitly declared chains in one local legacy PDB file. Report the deterministic heavy-atom residue contact set and minimum atom-pair distance at an explicit fixed cutoff. Exclude mmCIF, alternate conformers, multiple models, interface-area or pocket calculations, docking, molecular dynamics, affinity estimation, and functional claims."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Protein-interface Contact Analysis

`Preview + reviewed`; the helper self-test passed. Agent runtime, scientific
benchmarking, representative-structure testing, and expert review were not
performed.

## Owns

Compute a geometric residue-contact set between two named chains in one
bounded local legacy PDB file. A contact is not evidence of binding, affinity,
biological assembly, or function.

## Inputs and intake

Require a regular local PDB file, two distinct one-character nonblank chain
IDs, a fixed cutoff in `(0, 20]` angstrom, and a new JSON output path under the
current directory. Inspect safe facts first. Ask one unresolved question with
a recommendation, then wait:

1. **chain-pair.** Which exact two PDB chain IDs define the interface? Recommended: use chains from the intended biological assembly; never infer them from proximity.
2. **contact-cutoff.** Which preregistered heavy-atom cutoff applies? Recommended: use the study protocol value and report it exactly rather than tuning it after inspection.

An explicit local analysis request authorizes the bounded input read and new
report write.

## Run

```text
python3 scripts/analyze_contacts.py --input STRUCTURE.pdb \
  --chain-a A --chain-b B --cutoff 5.0 --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper includes `ATOM` and `HETATM` records,
requires element columns, excludes H/D/T, and refuses alternate locations and
multiple models. It accepts at most 32 MiB, 500,000 lines, 250,000 coordinate
records, 25,000 selected records per chain, and 10,000,000 cross-chain atom
comparisons. Larger or unsupported inputs return `needs-tool`.

## Output contract

`completed` contains input fingerprint, exact parameters and limits, per-chain
counts, and a sorted residue-pair contact list with the minimum atom pair and
distance. Zero contacts is a valid completed result. Invalid input or an
unsupported boundary creates no report.

Read [contact and runtime boundaries](references/contact-boundaries.md).

## Guardrails

- Never infer chains, biological assembly, cutoff, missing elements, alternate-conformer choice, or residue equivalence.
- Never overwrite, follow an input or output-path symlink, escape the current directory, use the network, start a subprocess, mutate the input, or publish a partial report.
- Exclude mmCIF, area or pocket analysis, docking, molecular dynamics, affinity estimation, and functional interpretation.
- Require researcher review; this preview has no clinical or diagnostic authority.
