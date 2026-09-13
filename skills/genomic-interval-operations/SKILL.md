---
name: genomic-interval-operations
description: "Merge or intersect same-build BED3 intervals with explicit coordinate, strand, duplicate and adjacency policies. Guide broader interval tasks only with a declared compatible tool; exclude liftover, peak calling and biological consensus claims."
license: Apache-2.0
metadata:
  version: "0.15.0"
---

# Genomic Interval Operations

Preview + reviewed. Small original helper checks are separate from Agent
benchmarks, whole-genome scaling and human expert review.

## Input and dialogue

Inspect available files and producer records first. Require exact build labels
for A, optional B and contig sizes, BED0 half-open coordinates, permission to
ignore strand, duplicate handling and (for merge) adjacency handling. Preserve
original input bytes. Complete authorized local requests proceed directly.

Ask one consequential missing question, explain its effect and recommend the
minimum useful record; wait on dependent work. Follow the existing
[dialogue guide](references/user-dialogue.md). Never infer assembly from contig
names, treat chr1/1 as aliases, or equate hg38 and GRCh38 without matching producer
records. Explain that [10,20) covers 10 bases; touching [20,30) shares zero bases.
BED3 has no strand field, so strand-sensitive questions need a different adapter.

## Bounded local execution

Use [operate_intervals.py](scripts/operate_intervals.py) with the
[local contract](references/local-adapter.md). Standard-library execution supports
exact BED3 merge/intersection, at most 2,000 rows per input and 20,000 overlap pairs.
Contig sizes define bounds and output chromosome order. No headers, comments,
extra BED columns or coordinate conversion are silently accepted.

- Merge one table using an explicit overlap-only or bookended policy. Preserve
  original-row membership in trace.tsv even when coordinates collapse.
- Intersect A/B using positive base overlap. Output one clipped BED3 row per
  overlapping pair, preserving multiplicity and A/B row identities in trace.tsv.
- Reject or preserve duplicate input rows as explicitly requested. Distinguish
  summed row widths from union coverage, which counts each base only once.
- Empty input/output is valid interval algebra. Do not fabricate one output row
  or interpret no overlap as proof of biological absence.

Return intervals.json, result.bed and trace.tsv in a new output directory,
including declarations, input/output hashes, row counts, union coverage and
limitations. Missing or conflicting facts return needs-decision; malformed data
return invalid-input; excessive rows/pairs return needs-tool without partial
output. Never overwrite, mutate inputs, install dependencies or use the network.

## Delivery and downstream use

Use the shared visualization (--kind intervals, --outcome CONTIG) for a diagram
of one explicitly selected contig and up to 60 rows. Preserve every displayed row;
this is an interval diagram, not genome-wide coverage or an inference plot.

A nonempty result.bed can enter existing chromatin-peak-set-qc as exact BED3 with
the same build and contig-size file. Empty results remain completed algebra;
the current peak QC requires nonempty sets, so report the empty result directly.
The shared report accepts both interval results and existing peak QC evidence.
The optional companion supports interval -> figure -> report; peak QC can be
included as fingerprinted report evidence without changing its legacy producer.

## Boundaries

Subtraction, nearest features and strand-aware operations require a separately
declared adapter; see [runtime boundaries](references/runtime-boundaries.md).
No liftover, name aliasing, peak calling, automatic gene annotation, consensus
peaks, differential accessibility or biological-quality interpretation. Overlap
is geometric evidence only. Preserve host permissions for any new side effect.
