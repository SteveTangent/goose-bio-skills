# Newick and runtime contract

This reference defines `phylogenetic-tree-io-and-qc` version `0.8.0`. The
bundled helper is an original, dependency-free implementation for a deliberately
small Newick subset.

## Exact input grammar

- Accept one non-empty UTF-8 file containing exactly one tree and one terminal
  semicolon. Allow whitespace between tokens.
- Allow leaves and internal nodes, parentheses, commas, optional node labels,
  and optional branch lengths after `:`. Require every tip to have a non-empty,
  case-sensitive label that is unique after parsing.
- Allow unquoted labels without whitespace or `()[],:;'`. Allow single-quoted
  labels and represent an embedded quote as two adjacent single quotes. Preserve
  every parsed label exactly; underscore remains underscore.
- Allow decimal or scientific-notation branch lengths. Require every supplied
  branch length, including a root length, to be finite and numerically
  nonnegative. Missing lengths are allowed and counted.
- Reject square-bracket comments, NHX annotations, Nexus, multiple trees,
  quoted branch lengths, empty child lists, and trailing content. These require
  a separately reviewed parser rather than a permissive fallback.

## Descriptive calculations

Count tips, internal nodes, all nodes, maximum root-to-node depth, root degree,
unary internal nodes, bifurcating internal nodes, and polytomies with more than
two children. Report branch-length presence, absence, zeros, minimum, maximum,
and sum.

If every individual branch length is finite but their aggregate exceeds the
finite floating-point range, keep the input valid and report `sum: null` with
`sum_status: not-estimable-numeric-overflow`.

Treat a finite numeric internal-node label as an uninterpreted numeric label.
Preserve nonnumeric internal labels as a separate count. Do not assume that a
numeric label encodes support or infer whether it is a proportion, percentage,
bootstrap value, posterior probability, or another convention. Values outside
0 through 100 are counted descriptively, not corrected or interpreted.

Hash the exact tip set as SHA-256 over a compact UTF-8 JSON array of sorted
parsed labels. `--compare-tree` validates both trees and requires those exact
sets to match. Case, quoting result, whitespace inside quoted labels, and
underscores remain significant; mismatch is recorded as `tip-set-mismatch`
with exact missing and extra labels in the create-new report.

## Safety, scale, and exclusions

Each input must be a stable regular non-symlink file below the current working
directory and no larger than 2 MiB. The parser accepts at most 10,000 nodes,
256 nesting levels, and 1,024 UTF-8 bytes per label. It writes one
create-exclusive JSON artifact below the same working directory, requires
existing non-symlink parents, and uses no network or subprocess. Unsupported
scale returns `needs-tool` and creates no report.

Exclude Nexus/NHX and comments, tree inference, alignment, rooting, pruning,
consensus or bootstrap generation, topology modification, visualization,
taxonomy reconciliation, and biological, evolutionary, clinical, or diagnostic
interpretation. The self-test covers a tiny synthetic tree only; it is not an
agent evaluation, representative-tree benchmark, parser-conformance suite,
scientific validation, or expert review.
