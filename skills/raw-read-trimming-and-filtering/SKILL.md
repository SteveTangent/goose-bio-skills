---
name: raw-read-trimming-and-filtering
description: "Use to trim declared adapters and apply an approved quality, length, or N-base filter to a small, explicitly listed local single-end or paired-end FASTQ set, producing new synchronized FASTQ files plus retention and provenance records. Exclude read download, QC interpretation, UMI handling, contamination classification, demultiplexing, deduplication, merging, alignment, broad batches, and overwrites."
license: Apache-2.0
metadata:
  version: "0.8.0"
---

# Raw Read Trimming and Filtering

`Preview + reviewed`; external-tool runtime skipped.

## Owns

Apply one declared policy to listed local FASTQ/FASTQ.GZ files; preserve inputs
and create new outputs.

## Inputs and intake

Accept a single-end list or unique R1/R2 map, adapter policy, filter thresholds,
and quality encoding when quality scores are used. Inspect pairing
and output safety.

Ask one unresolved result-changing question with a recommendation, then wait:

1. **adapter-policy:** if identity or orientation is unresolved, recommend library-preparation metadata; never guess a sequence.
2. **filter-policy:** if filter semantics or a required quality encoding are unresolved, recommend assay- and downstream-justified settings with enabled/disabled filters explicit.
3. **sample-map:** if sample or mate membership is ambiguous, recommend a unique map before processing.

## Workflow

1. Reject scans, interleaved input, large batches, duplicate stems, invalid FASTQ, mismatched pairs, insufficient space, and existing targets.
2. Select one adapter. Prefer Cutadapt for explicit matching; use fastp only with its full effective policy approved.
3. Record adapter provenance, filter semantics, paired behavior, outputs, and dry-run command.
4. Create a new directory exclusively and run once; never install, transfer data, or fall back.
5. Verify status, reports, FASTQ integrity, counts, mate synchronization, files, and hashes. Reconcile retained/removed units and warnings.

## Output contract

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. `completed` includes sample map, policy, adapter source,
command, versions, retention, files and hashes, warnings, limitations, and
follow-up checks. Never expose reads or invent execution.

## Guardrails

- Never mutate inputs or overwrite/reuse an output directory; label incomplete artifacts non-completed.
- Process mates together and state whether each filter acts on either or both.
- Retention, adapter detection, and a clean exit do not establish biological quality.
- Do not download, interpret QC, handle UMIs, classify contamination, demultiplex, deduplicate, merge, align, or use a network service.
- An unresolved required encoding is `needs-decision`; an incompatible encoding or long-read input is `needs-tool`. This preview owns a small short-read policy.
- Route large or batch inputs to `scientific-file-preflight-and-resource-planning`; skipped external-tool work is not passed.
- Require researcher review before accepting policy choices or downstream biological conclusions; no clinical authority.

Read [runtime boundaries](references/runtime-boundaries.md) before execution.
