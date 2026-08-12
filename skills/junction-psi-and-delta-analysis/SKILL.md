---
name: junction-psi-and-delta-analysis
description: "Use for bounded, offline calculation of per-sample percent-spliced-in (PSI) and a declared two-group PSI delta from a prepared long-form TSV of nonnegative integer inclusion and exclusion junction counts plus exact sample-group metadata. Require a prespecified minimum coverage and group direction. Exclude BAM or CRAM parsing, junction discovery, isoform reconstruction, statistical inference, differential gene expression, and biological or clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Junction PSI and Delta Analysis

`Preview + reviewed`; the deterministic helper self-test passed. Agent runtime,
representative-data benchmarking, scientific evaluation, and expert review were
not performed.

## Owns

Calculate PSI for each prepared event-sample pair that meets a declared minimum
coverage, then calculate an unweighted group-mean PSI and `group B - group A`
delta. Preserve low-coverage results as explicit not-estimable records.

## Inputs and intake

Require UTF-8 TSV files and a new JSON output path:

- counts: exact headers `event_id`, `sample_id`, `inclusion_count`, and
  `exclusion_count`, with one nonnegative-integer row per event-sample pair;
- groups: exact headers `sample_id` and `group`, with exactly the two declared
  labels and an exact sample join;
- declarations: distinct group-A and group-B labels plus integer minimum
  coverage of at least one.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **count-semantics.** Were inclusion and exclusion counts prepared under one
   compatible junction-counting rule? Recommended: use the producer-recorded
   event definition and counting rule; do not reinterpret raw alignments.
2. **contrast.** Which label is group A and which is group B? Recommended: use
   the prespecified design order because the reported delta is `B - A`.
3. **coverage.** What minimum total junction count was prespecified?
   Recommended: use the analysis protocol value rather than choosing a cutoff
   after viewing PSI values.

An explicit local analysis request authorizes the bounded reads and one
create-new report.

## Run

```text
python3 scripts/calculate_junction_psi.py \
  --counts PREPARED_COUNTS.tsv --groups SAMPLE_GROUPS.tsv \
  --group-a control --group-b treated --min-coverage 10 \
  --output NEW_REPORT.json
```

The dependency-free Python 3.10+ helper accepts regular, uncompressed files.
It safely pins each regular input leaf while allowing explicit absolute paths
and symlinked parent directories. It refuses leaf symlinks, malformed or
incomplete event-sample grids, ambiguous groups, invalid counts, and existing
outputs.

## Output contract

The deterministic create-new JSON report binds input fingerprints and declared
settings to per-sample coverage and PSI, group estimable counts and mean PSI,
and the declared `B - A` delta. Exact rational values accompany rounded decimal
values. Low coverage or a group with no estimable samples remains explicit; it
does not suppress the report.

Read [calculation contract](references/calculation-contract.md) before changing
the input preparation or interpreting not-estimable values.

## Guardrails

- Never parse BAM/CRAM, discover junctions, infer isoforms, or alter counts.
- Never choose event definitions, group order, or coverage from observed PSI.
- Never run hypothesis tests, multiple-testing correction, gene-level
  differential expression, or claim biological or clinical significance.
- Never overwrite, mutate inputs, create directories, use the network, or start
  a subprocess.
- Require researcher review of count provenance, event definitions, exclusions,
  and the descriptive output; this preview has no clinical authority.
