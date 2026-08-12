# Exact counting contract

## Input boundary

- Process one plain, uncompressed SAM sample and one plain, uncompressed GTF.
- Require at least one SAM `@SQ` entry and one primary single-end record.
- Treat SAM reference coordinates, CIGAR, FLAG, MAPQ, `NH`, and `RG` as the
  positional counting surface. Sequence/quality consistency and mate fields on
  unmapped records are not validated; establish full SAM validity upstream.
- Accept zero or more `@RG` headers, but require unique read-group IDs. When
  `SM` values are present, they must resolve to one exact sample and match the
  caller's sample ID; a primary record's `RG` tag must name a declared group.
- Require every counted GTF row to use feature type `exon`, positive one-based
  inclusive coordinates, `+` or `-` strand, and exactly one quoted `gene_id`.
- Require each `gene_id` to stay on one contig and strand. SAM may contain
  contigs without annotated exons, but a GTF exon contig absent from `@SQ` is
  invalid.

## Record selection

- Refuse mate-aware FLAG bits because this preview does not count fragments.
- Ignore secondary and supplementary records and report their counts.
- Do not exclude a primary record solely because its duplicate flag is set, and
  report the observed duplicate-flag count. Other categories such as QC failure
  still take precedence. This fixed policy is not a claim that duplicates are
  biologically independent.
- Assign QC-failed, unmapped, below-threshold MAPQ, and `NH>1` records to their
  own non-gene categories in that order.
- Accept a mapped record without `NH` by the declared MAPQ floor and report the
  number of such records. Do not claim the record is uniquely mapped.

## Exon overlap and strand

Interpret CIGAR `M`, `=`, and `X` spans as aligned reference blocks. Advance
over `D` and `N` without treating them as overlap; `I`, `S`, `H`, and `P` do not
advance the reference. A record overlaps a gene when any aligned block overlaps
any exon row for that `gene_id`.

- `unstranded`: accept either gene strand.
- `forward`: require the SAM read strand to equal the GTF gene strand.
- `reverse`: require the SAM read strand to differ from the GTF gene strand.

After strand filtering, assign exactly one compatible gene as `assigned`, more
than one as `ambiguous`, no genomic exon overlap as `no_feature`, and overlap
only with incompatible-strand exons as `wrong_strand`. Multiple transcript exon
rows for the same `gene_id` still represent one gene assignment.

## Interpretation boundary

The JSON rows are raw technical gene assignments for one sample. They are not
normalized expression, transcript abundance, statistical evidence, biological
quality, or a differential-expression result. Review reference identity,
library protocol, aligner-specific MAPQ/`NH` behavior, category proportions,
duplicate policy, and upstream SAM validity before downstream use.
