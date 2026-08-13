# Research Wave R2 candidates

Status: promoted into the v0.8.0 `main` Beta as `preview + reviewed` after the
minimum-reliability implementation passed on `research` and the atomic release
bound their final package and registry bytes.

Wave R2 adds three narrow jobs that cover different execution patterns: a
pure-local table check, a local interval workflow, and a pinned scientific tool
adapter. They were built in the order below for fast feedback; product priority
is noted separately.

## 1. Amplicon feature-table and taxonomy QC

Proposed slug: `amplicon-feature-table-and-taxonomy-qc`

Proposed placement: D07 / C18

Build order: 1; product priority: 3

Owns:

- validate a local TSV feature-count table, sample metadata, and optional
  taxonomy table;
- report joins, library sizes, zero-depth samples, sparsity, duplicate IDs,
  feature totals, taxonomy-rank completeness, and declared negative controls;
- preserve zero counts as observed zeros and report missing values separately.

Excludes FASTQ processing, denoising, chimera removal, taxonomy assignment,
BIOM/QZA parsing, rarefaction, diversity, differential abundance, contamination
decisions, pathogen diagnosis, and clinical interpretation.

Candidate-specific promotion gate:

- exact 4-feature by 4-sample TSV fixture with one negative control and one
  unclassified feature;
- two byte-identical local replays;
- reject negative or fractional counts, duplicate sample IDs, taxonomy-ID
  mismatch, ambiguous table orientation, and output overwrite;
- one positive routing case and two near-neighbor cases for read processing and
  downstream diversity/differential analysis;
- no network access and no QIIME dependency in the minimum version.

## 2. Chromatin peak-set QC

Proposed slug: `chromatin-peak-set-qc`

Proposed placement: D06 / C16

Build order: 2; product priority: 2

Owns:

- inspect at most four local BED or narrowPeak files whose caller-supplied build
  declarations are identical, against a contig-size file pinned to that build;
- report coordinate validity, out-of-range intervals, widths, duplicates,
  narrowPeak field validity, optional pinned-blacklist overlap, and descriptive
  pairwise overlap/Jaccard;
- use standard-library logic for the exact fixture and a pinned local bedtools
  canary only as an additional check.

Excludes read/BAM QC, peak calling, FRiP, IDR, consensus-peak construction,
differential accessibility, motif analysis, lift-over, and biological
reproducibility claims.

Candidate-specific promotion gate:

- two tiny peak files (one narrowPeak and one BED3) plus contig sizes and a
  blacklist fixture;
- exact assertions for half-open coordinates, one blacklist interval with exact
  row-hit and merged-base overlap counts, duplicates, widths, overlap, and
  base-coverage Jaccard (merged half-open intersection length divided by merged
  half-open union length), with two byte-identical replays;
- reject missing or explicitly mismatched build declarations, invalid columns,
  out-of-range coordinates, invalid peak offsets, symlink/output-boundary
  violations, and overwrite; never infer a genome build from coordinates, and
  report independently unverified build identity as such;
- one positive route plus near-neighbor routes for generic interval operations
  and peak calling;
- local bedtools version/hash provenance if the optional canary is retained.

## 3. Protein-level differential abundance

Proposed slug: `protein-level-differential-abundance`

Proposed placement: D08 / C22

Build order: 3; product priority: 1

Owns:

- analyze a finite protein-level matrix that the caller explicitly declares as
  normalized and log2-scaled, with exact sample metadata and one declared
  estimable contrast;
- run a pinned local R/limma adapter and record the design, contrast, tool
  versions, effect estimates, statistics, raw p-values, and adjusted p-values;
- fail closed when the adapter, declared scale, or design is unavailable.

Excludes raw mass-spectrometry processing, PSM/peptide inference, normalization,
imputation, count-based RNA differential expression, enrichment, biomarker
claims, and clinical interpretation.

Candidate-specific promotion gate:

- exact 6-protein by 6-sample fixture with a balanced batch term and one fixed
  contrast;
- two deterministic replays under pinned R and limma versions plus a small
  numerical oracle;
- reject duplicate samples, missing analysis cells, non-finite values, missing
  or explicitly non-log2 scale declarations, rank-deficient/confounded designs,
  unavailable adapter, and overwrite; never infer scale from the value
  distribution;
- one positive route plus near-neighbor routes for proteomics table QC,
  missing-data sensitivity, and count-based RNA differential expression;
- no fallback to an unreviewed t-test or a different statistical engine.

## Shared minimum gate

Every candidate must satisfy all of the following before a later atomic main
promotion:

1. one-job boundary, explicit inputs/outputs/exclusions, and no collision with
   an existing Skill;
2. complete package files, original/source-clean implementation, license and
   dependency boundary, and a matching registry digest on `research`;
3. one positive, one boundary/fail-closed, and at least one near-neighbor route;
4. retained small file-backed fixtures, two identical replays, input/output
   hashes, create-new publication, and no overwrite;
5. exact tool/network provenance for any adapter, while offline behavior remains
   honest and deterministic;
6. full repository skeleton checks, candidate self-tests, `git diff --check`,
   and independent review with P0=0 and P1=0;
7. remain `preview + reviewed`; minimum reliability does not establish formal
   scientific evaluation, generalization, performance, clinical use, or
   superiority over another repository;
8. promotion only through a new atomic collection version with final-byte
   digests, rollback entries, release evidence, main merge, and tag.

## Recorded Wave R2 minimum evidence

The retained offline replay in
[`run_wave_r2_minimal_reliability.py`](../scripts/run_wave_r2_minimal_reliability.py)
passed twice with 67/67 checks and byte-identical outputs. It binds the three
package digests, small input hashes, deterministic output hashes, valid and
invalid paths, self-tests, and create-new/no-overwrite behavior. The canonical
routing set now contains 53 cases, including positive and near-neighbor cases
for all three candidates. A separate evaluator that was not shown the eval
files selected the expected Skill or no-Skill boundary in 6/6 Wave R2 prompts
with zero forbidden selections.

Independent review found no open P0, P1, or accepted P2 finding in the frozen
candidate packages. This is deliberately small synthetic release evidence:
runtime evaluation, representative scientific benchmarking, expert review,
generalization, clinical use, and superiority claims remain not performed.
The exact scope and remaining evidence are recorded in
[`research-wave-r2-minimal-reliability-v0.1.json`](../evals/research-wave-r2-minimal-reliability-v0.1.json).

## Not in this wave

Single-cell automatic annotation, variant-consequence annotation, raw-read
alignment, spatial analysis, and clinical interpretation remain deferred because
their reference, expert-review, compute, or safety boundaries are substantially
larger than this quick minimum-reliability wave.
