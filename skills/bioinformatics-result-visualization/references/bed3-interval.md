# BED3 algebra delivery

Use --kind intervals --result intervals.json --outcome CONTIG --output NEW_DIRECTORY
for a completed goose_bed3_intervals 0.15.0 result. Choose one exact contig; the
figure displays every input/output row on that contig, up to 60 rows. Other
contigs remain in the source JSON and report summaries, not silently combined
in the figure. Empty results are allowed. No inferential interpretation is added.

The report accepts --report intervals=intervals.json peak_qc=peak-qc.json and
optional --figure interval_map=FIGURE_DIRECTORY, with --language zh. Interval row
length sums and union coverage have different meanings; multiplicity can inflate
row-length sums. Preserve assembly/coordinate/strand/adjacency declarations.

Existing chromatin-peak-set-qc JSON is accepted as report evidence. That producer
is unchanged and is not a new native companion format. For nonempty result.bed,
run the existing peak QC with --peak-format bed, matching --peak-build and the same
contig-size input. An empty algebra result remains valid; skip the nonempty-only
peak QC and state that boundary. Jaccard/overlap/merge does not establish quality,
biological consensus or significance.
