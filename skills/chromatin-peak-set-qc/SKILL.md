---
name: chromatin-peak-set-qc
description: "Use for bounded, offline QC of up to four local BED3 or narrowPeak files against caller-declared identical reference-build labels, a matching contig-size file, and an optional matching BED3 blacklist. Report coordinate and field validity, bounds, widths, duplicate coordinates, blacklist overlap, and descriptive pairwise base-coverage Jaccard. Exclude BAM/read QC, peak calling, FRiP, IDR, consensus peaks, differential accessibility, motif analysis, lift-over, and biological reproducibility claims."
license: Apache-2.0
metadata:
  version: "0.9.0"
---

# Chromatin Peak-set QC

`Preview + reviewed`; the helper self-test passed. Agent runtime, representative
genome-scale testing, scientific benchmarking, and expert review were not
performed.

## Owns

Check the syntax and descriptive interval properties of one to four local peak
sets under an exact caller-declared same-build contract. Pairwise Jaccard is a
base-coverage summary, not evidence of biological or technical reproducibility.

## Inputs and intake

Require one to four regular local BED3 or narrowPeak files, one regular local
two-column contig-size file, an exact build declaration for every peak file and
the contig sizes, and a new JSON output path. An optional blacklist must be a
local BED3 file with its own exact matching build declaration.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **build-contract.** Which exact build label applies to every input? Recommended: use the producer-recorded build label and a contig-size file pinned to the same release; never infer build from coordinates.
2. **format-contract.** Is each peak file exact BED3 or narrowPeak? Recommended: use the producer-declared format and reject ambiguous or mixed-width rows.
3. **blacklist-contract.** Is a blacklist required, and which exact build does it use? Recommended: omit it unless a specific pinned local blacklist is part of the protocol.

An explicit local QC request authorizes the bounded reads and one create-new
report.

## Run

```text
python3 scripts/check_peak_sets.py \
  --contig-sizes BUILD.chrom.sizes --contig-build GRCh38 \
  --peak replicate-1.narrowPeak --peak-format narrowPeak --peak-build GRCh38 \
  --peak replicate-2.bed --peak-format bed --peak-build GRCh38 \
  [--blacklist pinned-blacklist.bed --blacklist-build GRCh38] \
  --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper treats BED coordinates as zero-based,
half-open. `bed` means exact BED3; `narrowPeak` means exactly ten fields. It
refuses leaf input symlinks, unsafe output paths, existing outputs, unsupported
scale, mixed or missing declarations, invalid fields, unknown contigs, and
out-of-range or zero-width intervals.

## Output contract

The deterministic create-new JSON report binds input fingerprints and exact
declarations to per-file interval counts, merged coverage, width totals/ranges,
duplicate-coordinate counts, optional blacklist overlap, and every pairwise
intersection, union, and Jaccard. Jaccard is exactly merged half-open base
coverage intersection length divided by union length.

Read [format and runtime boundaries](references/format-and-runtime-boundaries.md).

## Guardrails

- Never infer, normalize, alias, or lift a genome build or contig name.
- Never convert overlap, Jaccard, or blacklist counts into reproducibility, quality, or biological conclusions.
- Never overwrite, mutate inputs, follow leaf input or output-parent symlinks, use the network, or start a subprocess.
- Exclude BAM/read QC, peak calling, FRiP, IDR, consensus construction, differential accessibility, motif analysis, and lift-over.
- Require researcher review of build provenance, blacklist choice, and interpretation; this preview has no clinical or diagnostic authority.
