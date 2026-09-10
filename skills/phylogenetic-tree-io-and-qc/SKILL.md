---
name: phylogenetic-tree-io-and-qc
description: "Parse and check one or two local Newick trees for structural and identifier consistency. Exclude tree inference, pruning, rooting changes and evolutionary conclusions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Phylogenetic Tree I/O and QC

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-tree testing, scientific evaluation, and expert review were not
performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use for bounded, offline structural QC of one local single-tree Newick file and optional exact tip-set comparison with a second Newick file. Validate parsing, unique nonempty tip labels, and finite nonnegative branch lengths; report topology shape, polytomies, and numeric internal labels without assigning support semantics. Exclude Nexus/NHX, alignment, tree inference, rooting, pruning, consensus or bootstrap generation, visualization, taxonomy reconciliation, and biological or evolutionary interpretation.

## Owns

Parse one bounded local Newick tree, reject unsafe or ambiguous structure, and
write a descriptive structural QC report. Optionally require a second valid
Newick tree to have exactly the same tip-label set.

## Inputs and intake

Require one UTF-8 single-tree Newick file and a new JSON output path. For exact
tip-set comparison, require a second file. Run from a non-symlink working
directory that contains every input and the output parent.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **comparison-contract.** Must another tree contain exactly the same tips?
   Recommended: supply `--compare-tree` only when exact, case-sensitive label
   equality is required; do not normalize underscores, whitespace, or aliases.

An explicit local QC request authorizes the bounded reads and one create-new
report.

## Run

```text
python3 scripts/qc_newick_tree.py \
  --tree TREE.nwk --output NEW_REPORT.json \
  [--compare-tree OTHER_TREE.nwk]
```

The dependency-free Python 3.10+ helper accepts one semicolon-terminated tree,
unquoted or single-quoted labels, and ordinary decimal/scientific branch
lengths. It refuses missing or duplicate tip labels, negative or non-finite
branch lengths, unsupported comments/dialects, unsafe paths, symlinks,
unsupported scale, and existing outputs.

## Output contract

The deterministic create-new JSON report binds the input fingerprint to tip,
internal-node, depth, unary-node, bifurcation, polytomy, branch-length, and
internal-label summaries. Numeric internal labels are reported descriptively
without assuming that they encode support or inferring their meaning. Optional comparison
records either an exact match or a `tip-set-mismatch` diagnostic with the
missing and extra labels. A mismatch is a QC finding, so it still creates the
requested report; malformed or unsafe inputs do not.

Read [the exact Newick and runtime contract](references/newick-contract.md).

## Guardrails

- Never infer, reroot, prune, collapse, resolve, annotate, or rewrite a tree.
- Never normalize labels or interpret topology, support, distance, ancestry, species relationships, or evolutionary validity.
- Never overwrite, mutate inputs, create directories, follow input/output symlinks, use the network, or start a subprocess.
- Exclude Nexus/NHX, comments, multiple trees, alignments, inference, consensus or bootstrap generation, visualization, and taxonomy reconciliation.
- Require researcher review of producer format, label identity, support convention, and biological interpretation; this preview has no clinical or diagnostic authority.
