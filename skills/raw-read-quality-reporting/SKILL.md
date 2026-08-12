---
name: raw-read-quality-reporting
description: "Use to generate or interpret read-quality reports for a small, user-provided local FASTQ set or existing FastQC reports. FastQC is primary; MultiQC may only aggregate existing reports. Exclude read download, trimming, alignment, large or batch QC, contamination classification, and experimental pass/fail decisions."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Raw Read Quality Reporting

`Preview + reviewed`; FastQC and MultiQC runtime execution was skipped.

## Owns

Create an assay-aware report from a few local FASTQ files or explain existing
FastQC results. MultiQC only aggregates generated reports.

## Inputs and intake

Accept an explicit local list of FASTQ/FASTQ.GZ files, `_fastqc.zip` archives,
or extracted `fastqc_data.txt` plus `summary.txt`, with an optional sample map.
Inspect sizes, metadata, tool availability, and versions first.
Ask one unresolved result-changing question with a recommendation, then wait:

1. **report-source:** if raw files and reports cannot be matched, recommend treating them separately or generating new reports.
2. **library-context:** if expected library context is missing, recommend using documented assay and preparation details.
3. **sample-map:** if sample or mate membership is ambiguous, recommend an explicit unique map.

An explicit safe local request authorizes bounded reads and new outputs; do not
repeat confirmation unless scope or side effects change.

## Workflow

1. Reject directory scans, large batches, duplicate output stems, and existing targets. Inventory every input.
2. For raw FASTQ, run the reviewed FastQC command only when compatible; otherwise return `needs-tool` with a dry-run command.
3. Inspect every report, not only summary flags. Interpret quality, composition, duplication, length, adapter, overrepresented-sequence, and tile findings in context.
4. Compare mates and samples without merging their evidence. Run MultiQC only when the user requests aggregation of already generated reports.
5. Reconcile samples and outputs; record failures, skips, commands, versions, and researcher decisions.

## Output contract

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. `completed` includes inventory, versions, per-sample evidence,
contextual interpretation, comparisons, artifacts, limitations, and follow-up
checks. Never include reads or claim an unobserved run.

## Guardrails

- FastQC `warn` and `fail` are attention signals, not experimental success, sample rejection, or automatic trimming decisions.
- Keep R1/R2 and assay-specific expected biases explicit; never impose one universal QC profile.
- Do not download, trim, filter, align, classify contamination, upload, or use a network service.
- Write only to approved new locations; never mutate FASTQ files or overwrite reports.
- Route large or batch inputs to `scientific-file-preflight-and-resource-planning`; skipped external-tool work is not passed.
- Require researcher review for biological interpretation; no clinical authority.

Read [runtime boundaries](references/runtime-boundaries.md) before running or aggregating reports.
