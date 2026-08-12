# Research Wave R3 candidates

Status: minimum research gate passed on `research`. These entries are not part
of the v0.7.0 Beta and are not authorized for direct `main` promotion. A later
atomic collection release must bind their final bytes.

Wave R3 combines two fast, deterministic local checks with one strategically
important reads-to-alignment handoff. Each candidate owns one narrow job.

## 1. Phylogenetic tree I/O and QC

Proposed slug: `phylogenetic-tree-io-and-qc`

Proposed placement: D02 / C08

Owns:

- inspect one bounded local Newick tree and optionally compare its exact tip
  set with a second local Newick tree;
- report parsing status, duplicate tips, branch-length validity, topology
  counts, polytomies, and numeric internal-label presence in deterministic JSON;
- preserve the input topology and report uncertainty instead of rewriting it.

Excludes tree inference, alignment, model selection, rooting, pruning,
consensus construction, visualization, dating, ancestral reconstruction, and
biological interpretation.

Candidate-specific minimum gate:

- two tiny Newick trees with one exact tip-set match;
- two byte-identical local replays and exact structural assertions;
- reject malformed trees, duplicate tips, negative or non-finite branch
  lengths, incompatible tip sets, symlink/output-boundary violations, and
  overwrite;
- one positive route plus near-neighbor routes for sequence alignment and tree
  inference;
- no network access and no external tree-inference dependency.

## 2. Untargeted metabolomics feature-table QC

Proposed slug: `untargeted-metabolomics-feature-table-qc`

Proposed placement: D08 / C23

Owns:

- inspect a bounded feature-by-sample TSV plus exact sample metadata under
  caller-declared intensity, zero, and missing-value semantics;
- report joins, duplicate identifiers, finite nonnegative intensities,
  detected and missing counts, pooled-QC RSD, blank/study descriptive ratios,
  and batch/injection-order completeness;
- emit `not-estimable` when the small table cannot support a declared summary.

Excludes raw-MS peak picking, alignment, drift correction, filtering,
normalization, imputation, compound annotation, differential analysis, pathway
analysis, and automated quality or contamination decisions.

Candidate-specific minimum gate:

- one tiny feature table with pooled-QC, blank, and study samples plus matching
  metadata;
- two byte-identical local replays and exact arithmetic assertions;
- reject negative, non-finite, duplicate, mismatched, ambiguously oriented, or
  overwrite inputs while preserving zero separately from missing;
- one positive route plus near-neighbor routes for raw-MS processing and
  downstream statistical analysis;
- no network access and no mandatory metabolomics framework dependency.

## 3. Read alignment selection and execution

Proposed slug: `read-alignment-selection-and-execution`

Proposed placement: D02 / C05

Owns:

- execute one explicit local branch only: bounded single-end short-read DNA
  FASTQ against one exact local reference FASTA with a caller-supplied reviewed
  `minimap2` executable;
- publish a new SAM plus deterministic mapping counts, command arguments, tool
  identity, and input/reference/output digests;
- return `needs-tool` when the fixed adapter is unavailable rather than using
  an unreviewed fallback.

Excludes read QC and trimming, paired-end data, RNA/splice alignment, long
reads, reference discovery, sorting/indexing and other BAM operations, variant
calling, quantification, and multi-aligner benchmarking.

Candidate-specific minimum gate:

- tiny exact reference and single-end FASTQ fixtures with a bounded reviewed
  adapter contract;
- two byte-identical deterministic reports and exact SAM/count assertions;
- retain adapter-contract and fail-closed evidence, plus a separately recorded
  real-tool canary, without treating that narrow synthetic run as formal agent
  runtime or scientific evaluation;
- reject malformed FASTQ/FASTA, paired-end or unsupported assay requests,
  reference/input changes, unsafe or nonregular resolved targets, unsafe output
  paths, and overwrite; ordinary input and executable symlinks are accepted only
  after their final regular targets are resolved and pinned;
- one positive route plus near-neighbor routes for trimming and existing
  alignment-file operations;
- no shell invocation, environment inheritance, automatic tool installation,
  or fallback aligner.

## Shared minimum gate

Every Wave R3 candidate must pass:

1. one-job boundaries and explicit near-neighbor exclusions;
2. source-clean package, license, manifest, interface, permission policy, and
   matching research-registry digest;
3. positive, invalid, fail-closed, and near-neighbor routes;
4. retained tiny file-backed fixtures, two identical replays, exact hashes,
   create-new publication, and no overwrite;
5. deterministic bundled self-tests and honest tool/runtime provenance;
6. full repository checks and independent review with P0=0 and P1=0;
7. `preview + reviewed` only: no formal scientific, generalization, clinical,
   performance, or superiority claim;
8. promotion only through a new atomic collection version with final-byte
   evidence and rollback entries.

## Recorded Wave R3 minimum evidence

The retained offline replay in
[`run_wave_r3_minimal_reliability.py`](../scripts/run_wave_r3_minimal_reliability.py)
passed twice with 60/60 checks and byte-identical events. It binds all three
package digests, small input and output hashes, deterministic self-tests,
invalid and fail-closed paths, and create-new/no-overwrite behavior. The
canonical routing set contained 62 cases at the Wave R3 gate, and an independent evaluator selected
the expected Skill or no-Skill boundary for all six Wave R3 holdout prompts
with no forbidden selections or unnecessary questions.

Independent package review at the original Wave R3 gate found no open P0, P1,
or P2 finding. The later cross-wave final publisher seal review closed all P0/P1
findings and retained one accepted non-blocking P2 for the documented low-level
local-directory concurrency and exceptional temporary-file cleanup boundary.
This remains a small minimum. A later synthetic macOS ARM64 canary ran the exact executor twice
with real minimap2 2.31-r1302, produced byte-identical SAM and report artifacts,
and passed create-new/no-overwrite checks. It did not add representative
scientific benchmarking, formal agent evaluation, expert review, scale,
generalization, clinical use, or superiority evidence. The exact scopes are in
[`research-wave-r3-minimal-reliability-v0.1.json`](../evals/research-wave-r3-minimal-reliability-v0.1.json)
and
[`research-wave-r3-minimap2-canary-v0.1.json`](../evals/research-wave-r3-minimap2-canary-v0.1.json).
