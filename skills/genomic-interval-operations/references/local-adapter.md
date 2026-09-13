# Same-build BED3 local adapter 0.15.0

Python >=3.10 standard library; input files at most 8 MiB, 2,000 intervals per BED,
10,000 contigs, 20,000 positive-overlap pairs. No subprocess or network.

Inputs are ASCII exact tab-separated rows, without headers/comments/track lines.
BED3: chrom, start, end; coordinates are integers with 0 <= start < end <= length.
Contig sizes: chrom, length (1..2^31-1); unique names define output order.
Empty BED files are valid; contig sizes cannot be empty. Reject extra BED/narrowPeak
fields rather than silently dropping their meaning. Original row IDs are 1-based
file row numbers; contig tokens and build labels are exact, never normalized.

```text
python3 scripts/operate_intervals.py --a A.bed --b B.bed --contigs toy.chrom.sizes \
  --operation intersect --build-a toy-v1 --build-b toy-v1 --contig-build toy-v1 \
  --coordinate-system bed0-half-open --strand-policy ignore --duplicates preserve \
  --output NEW_DIRECTORY

python3 scripts/operate_intervals.py --a A.bed --contigs toy.chrom.sizes \
  --operation merge --adjacency overlap-only --build-a toy-v1 --contig-build toy-v1 \
  --coordinate-system bed0-half-open --strand-policy ignore --duplicates preserve \
  --output ANOTHER_NEW_DIRECTORY
```

For merge, bookended joins touching intervals; overlap-only does not. It never
bridges a positive gap. The merged geometry naturally collapses duplicate intervals;
trace.tsv retains each contributing row. For intersection, each qualifying pair
has max(startA,startB) < min(endA,endB); touching boundaries are not hits. No
fractional-overlap threshold, left join or nearest-feature mode is hidden behind
this command. Positive intersections remain separate rows even when identical.

Duplicate policy reject refuses repeated coordinates within either source table;
preserve retains multiplicity. Output rows are ordered by contig dictionary,
start, end and source row. Output row IDs refer to this resulting order.

intervals.json contains config, caller-declared reference, parsed input rows,
results, trace, counts/coverage, runtime version and SHA-256 inventories.
result.bed is header-free; trace.tsv has output_row/a_row for merge, plus b_row
and overlap_bp for intersection. output_row_bp_sum can count shared bases repeatedly;
output_coverage_bp is a union, independent of duplicate rows. No Jaccard or
significance test is calculated here.

Empty result.bed has zero bytes and is a successful result. The shared report
can describe it; existing peak-set QC rejects empty peak files, so skip that
optional downstream QC for empty results. For nonempty output, pass exact bed
format, unchanged contig sizes and the same recorded build. Do not rename an
intersection result as consensus peaks or nearest genes.

Build/convention/strand uncertainty returns needs-decision before publishing.
Invalid coordinates/unknown contigs/duplicates under reject return invalid-input.
A resource cap returns needs-tool; no result bundle is written. Directory creation
is create-new only. Trusted output identities can be registered with the existing
companion; it does not execute this helper or establish biological suitability.
