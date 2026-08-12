# Format and runtime boundaries

This reference defines `chromatin-peak-set-qc` version `0.7.0`. The bundled
helper is an original, dependency-free implementation.

## Exact input contract

- Accept one to four non-empty peak files. Format `bed` means exactly three
  tab-separated columns; `narrowPeak` means exactly ten tab-separated fields.
- Treat every interval as zero-based and half-open: `start >= 0`, `end > start`,
  and `end <=` the exact named contig size. Do not normalize contig names.
- Require a finite positive contig size for every uniquely named contig in the
  two-column tab-separated contig-size file.
- Require every caller-supplied build label to be non-empty and byte-for-byte
  identical. The helper neither recognizes nor independently verifies labels.
- For narrowPeak, require score as an integer from 0 through 1000; strand as
  `+`, `-`, or `.`; finite nonnegative signal value; p- and q-values as either
  `-1` or finite nonnegative values; and peak as `-1` or a zero-based integer
  offset strictly smaller than interval width.
- If supplied, the blacklist is exact BED3 under the same declared build and
  coordinate contract.

The BED coordinate and narrowPeak field definitions were checked against the
[UCSC Genome Browser format FAQ](https://genome.ucsc.edu/FAQ/FAQformat.html) on
2026-08-12. That format review does not validate build identity, blacklist
choice, biological interpretation, or this implementation.

## Descriptive calculations

Merge each file independently by exact contig, joining overlapping or
bookended half-open intervals. Bookended merging does not change base coverage.
For a pair of peak sets, calculate intersection length with a deterministic
two-pointer scan of the merged intervals. Report union as
`coverage_a + coverage_b - intersection`; Jaccard is intersection divided by
union. Also report the exact integer numerator and denominator.

Duplicate coordinates are repeated `(contig, start, end)` rows within one file,
regardless of other narrowPeak fields. Blacklist-hit row counts include each
input row; blacklist-overlap bases use merged coverage and therefore do not
double-count duplicate or overlapping bases.

These are descriptive set summaries. They do not establish assay quality,
replicate agreement, biological reproducibility, or a preferred peak set.

## Safety, scale, and exclusions

Each input is a stable regular non-symlink file no larger than 16 MiB. The
helper accepts at most 250,000 data rows per file and 500,000 peak rows in one
run. It writes one create-exclusive JSON artifact below the current directory,
requires existing non-symlink parents, and uses no network or subprocess.
Unsupported scale returns `needs-tool` and creates no report.

Exclude compressed/binary files, BAM/read QC, peak calling, FRiP, IDR,
consensus-peak construction, differential accessibility, motif analysis,
lift-over, build inference, and clinical or biological interpretation. The
self-test covers exact coordinates and Jaccard, one blacklist overlap,
duplicates, narrowPeak fields, determinism, mismatched builds, malformed and
out-of-range records, symlink refusal, output-root boundaries, and no-overwrite
publication. It is not an agent evaluation, representative-data benchmark, or
expert review.
