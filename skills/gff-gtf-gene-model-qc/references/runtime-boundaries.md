# Rule and runtime boundaries

This reference defines the exact scope of `gff-gtf-gene-model-qc` version
`0.7.0`. The bundled checker is an original, dependency-free implementation.

## Structural rules

For both dialects, the checker requires exactly nine tab-separated columns,
positive one-based inclusive coordinates, allowed strand and phase tokens, an
exact contig-name match, and coordinates no larger than the declared contig.
It counts every parsed feature type. A CDS must carry phase `0`, `1`, or `2`;
the checker does not reconstruct translation or prove phase continuity across
CDS segments.

For GFF3, it reads `ID` and comma-separated `Parent` values after bounded
attribute parsing. Every parent must resolve to one unambiguous ID. Exact or
conflicting duplicate declarations are errors; repeated compatible IDs are
reported for review because they may denote a discontinuous feature. Parent and
child must use the same contig and compatible strand, and the child interval
must be contained by the declared parent. Self-parent and multi-record parent
cycles are errors. Content after `##FASTA` is not parsed.

Parsing stops before unbounded expansion: one record may be at most 1 MiB, one
feature may name at most 1,024 parents, and one annotation may retain at most
250,000 Parent references. Cycle examples show at most 20 bounded identifiers;
full per-rule counts remain available. `parent-cycle` counts DFS back-edge
detections: it proves cyclic structure but does not enumerate distinct simple
cycles.

For GTF, `gene_id` and `transcript_id` form the hierarchy. Gene and transcript
declarations must be unique. Transcript parents and common gene-model child
features (`exon`, `CDS`, UTR, and start/stop codons) must resolve within the
supplied file and satisfy contig, strand, and containment checks.

## Reviewed format sources

| Format surface | Reviewed source | Checked |
| --- | --- | --- |
| GFF3 columns, attributes, `ID`, `Parent`, and hierarchy | [Sequence Ontology GFF3 specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md) | 2026-08-10 |
| GTF nine-column, one-based inclusive feature and attribute conventions | [Ensembl GFF/GTF format](https://www.ensembl.org/info/website/upload/gff.html?redirect=no) | 2026-08-10 |
| `.fai` name and sequence-length columns | [HTSlib faidx format](https://www.htslib.org/doc/faidx.html) | 2026-08-10 |

These sources define the narrow syntax and coordinate surface reviewed here;
they do not establish biological completeness or producer-specific validity.

## Finding semantics

The report distinguishes a completed audit from its structural outcome.
Malformed records, missing parents, duplicate declarations, invalid CDS phase,
out-of-range coordinates, and parent-child conflicts produce structural
errors. Capped examples prevent a broken file from flooding the report, while
full per-rule occurrence counts are retained.

Exact contig names are intentional. `chr1` and `1` are not treated as equal,
because silently normalizing them can hide an assembly or producer mismatch.
Contigs present only in the size table are summarized but are not failures.

## Exclusions and verification status

The checker does not repair files, infer missing features, identify an
assembly, perform lift-over or interval algebra, run gene prediction, measure
BUSCO/OMArk-style completeness, assign functions, calculate protein-length or
mono-exonic heuristics, or judge biological model quality.

The deterministic self-test covers clean and broken synthetic GFF3/GTF,
orphan, duplicate, cyclic, and cross-gene identifiers, containment, CDS phase, contig bounds,
record caps, leaf-symlink refusal, and no-overwrite publication. It is not agent
runtime evidence, a scientific benchmark, large-file calibration, or expert
review. The package remains `preview + reviewed`.
