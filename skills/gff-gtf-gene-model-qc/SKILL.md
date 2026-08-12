---
name: gff-gtf-gene-model-qc
description: "Use for bounded, read-only structural QC of an explicitly named local GFF3 or GTF gene-model file against an explicit .fai or contig-size table. Report feature counts, identifier hierarchy, orphan or repeated identifiers, CDS phase fields, parent containment, coordinate bounds, and exact contig consistency. Exclude repair, prediction, completeness scoring, functional annotation, interval algebra, and biological-quality claims."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# GFF/GTF Gene-model Structural QC

`Preview + reviewed`; the helper self-test passed. Agent runtime, large-file
calibration, scientific benchmarking, and expert review were not performed.

## Owns

Audit one declared local GFF3 or GTF annotation against one exact contig
dictionary. This does not establish biological accuracy or completeness.

## Inputs and intake

Require an explicit annotation path, `gff3` or `gtf`, an explicit `.fai` or
two-column contig-size path, and a new JSON report path. Inspect safe facts
first. Ask one unresolved question with a recommendation, then wait:

1. **annotation-dialect.** Is the ninth column GFF3 or GTF syntax? Recommended: use the producer's declared format; do not infer it from mixed attributes.
2. **contig-dictionary.** Which exact assembly `.fai` or contig-size table governs coordinates? Recommended: use the dictionary created from the same reference release as the annotation.

An explicit local QC request authorizes these bounded reads and the new report.

## Run

```text
python3 scripts/check_gene_models.py \
  --annotation ANNOTATION --format gff3|gtf \
  --contig-sizes REFERENCE.fa.fai --output NEW_REPORT.json
```

The Python 3.10+ helper accepts uncompressed UTF-8 regular files only. Limits
are 64 MiB, 250,000 rows, 1 MiB/record, 1,024 parents/feature, 250,000 Parent
references, an 8 MiB size table, and 100,000 contigs. It refuses leaf symlinks,
parent traversal, and existing output paths.

## Output contract

The create-new JSON report contains fingerprints, limits, counts, capped
examples, full per-rule counts, and structural status. Exit `0` means no errors
found, `1` means a completed report with errors, and `2` means no completed audit.

Missing choices are `needs-decision`; unsupported scale or compression is
`needs-tool`; unsafe or unreadable input is `invalid-input`. Read [rule and
runtime boundaries](references/runtime-boundaries.md).

## Guardrails

- Match contig names exactly; never silently strip or add a `chr` prefix.
- Treat unresolved or ambiguous parentage as a finding, not an inferred link.
- Never overwrite, follow a leaf symlink, recurse, decompress, use the network, or start a subprocess.
- Exclude repair, prediction, completeness scoring, functional annotation, interval algebra, translation reconstruction, and biological interpretation.
- Require researcher review; this preview has no clinical or diagnostic authority.
