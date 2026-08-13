# Exact matrix-assembly contract

## Accepted source reports

Accept two through 128 regular, UTF-8 JSON files inside the current working
directory. Each file must be at most 64 MiB, contain no duplicate object key,
and declare all of the following:

- `schema_version` exactly `1.0`, `status` exactly `completed`, and
  `analysis_performed` exactly `true`;
- adapter name `count_gene_alignments` and a nonempty adapter version;
- one unique, bounded sample ID;
- a lowercase SHA-256 at `inputs.gtf.sha256`;
- positive integer `inputs.gtf.gene_count` and `inputs.gtf.exon_count` values
  that exactly reconcile to the published gene rows;
- the complete fixed schema-1.0 assignment contract;
- one through 100,000 unique gene rows with exactly `gene_id`, `contig`,
  `strand`, `exon_count`, and `count`.

Identifiers must be nonempty, trimmed, contain no control character, and be at
most 256 Unicode code points. Strand is `+` or `-`; exon count is a positive
integer; raw count is a nonnegative JSON integer no greater than
9,007,199,254,740,991. JSON booleans and floating-point values are not integers.
The total matrix may contain at most 5,000,000 gene-count cells.

## Equality boundary

Use the lexically smallest sample ID as the deterministic reference report.
Require every other report to match it exactly on:

1. the GTF SHA-256;
2. the set of gene IDs and every gene's `(gene_id, contig, strand,
   exon_count)` tuple; and
3. the complete assignment-contract object, including MAPQ and strandedness.

Do not infer equivalence, reconcile aliases, accept subsets, fill absent genes,
or coerce values. A mismatch invalidates the whole assembly and leaves no final
output.

## Deterministic output

Sort sample IDs and gene IDs by Unicode code-point order. Each gene row's
`counts` array follows the published sample order. Canonical JSON uses UTF-8,
two-space indentation, sorted object keys, and one trailing newline. Record each
source file's byte count and SHA-256 but never its local path. Reversing input
argument order must produce identical bytes.

Publication uses a create-new staged file. Tested exception rollback begins
after the staged file identity is recorded. A crash or a rare pre-identity
failure can leave a hidden mode-0600 stage; publication is not crash-atomic and
assumes no malicious writer is racing in the same output directory.

## Interpretation boundary

The result is a lossless structural join of raw technical assignments. Exact
contract agreement does not prove reference correctness, sample comparability,
sequencing adequacy, count validity, independence, or experimental-design
suitability. No normalization, transformation, filtering, imputation, batch
correction, statistical test, differential-expression model, biological claim,
or clinical decision is performed.
