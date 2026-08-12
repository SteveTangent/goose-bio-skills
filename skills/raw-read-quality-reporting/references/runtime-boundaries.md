# Runtime and scientific boundaries

This reference defines the operating boundary for
`raw-read-quality-reporting` version `0.7.0`. Interfaces were reviewed from
official documentation on 2026-08-10; neither tool was executed.

## Scientific contract

- FastQC is the primary analysis adapter. Inspect individual module evidence in the assay, library-preparation, platform, read-layout, and expected-bias context.
- A green, orange, or red module status is a pointer for review. It is not an experimental pass/fail decision, an automatic sample-exclusion rule, or an automatic trimming instruction.
- Keep paired mates and samples separate. Explain shared and discordant patterns without averaging away module evidence.
- MultiQC only parses already generated FastQC results for comparison. It does not analyze FASTQ reads and does not replace individual FastQC reports.

## Reviewed local interfaces

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| FastQC | 0.12.1; local non-interactive FASTQ report generation | [official download](https://www.bioinformatics.babraham.ac.uk/projects/download.html), [result interpretation](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/2%20Basic%20Operations/2.2%20Evaluating%20Results.html) | 2026-08-10 |
| MultiQC | 1.35; local FastQC-result aggregation only | [official release](https://github.com/MultiQC/MultiQC/releases/tag/v1.35), [FastQC module](https://docs.seqera.io/multiqc/modules/fastqc), [running MultiQC](https://docs.seqera.io/multiqc/getting_started/running_multiqc) | 2026-08-10 |

These are compatibility surfaces, not bundled dependencies. Record the exact
installed version before execution; do not install or upgrade a tool silently.

## Command boundary

Use an explicit bounded file list and a user-approved, pre-created new empty
output directory. Preflight unique input basenames because FastQC derives
report names from input names. The reviewed FastQC shape is:

```text
fastqc --version
fastqc --noextract --threads 1 --outdir <new-empty-fastqc-output-dir> \
  <input.fastq.gz> [additional-explicit-inputs]
```

FastQC normally creates one self-contained HTML report and one `_fastqc.zip`
archive per input. Verify exit status, expected files, non-empty outputs, and
one-to-one input coverage before claiming completion.

Only after FastQC reports exist, optional aggregation may use:

```text
multiqc --version
multiqc --no-version-check --no-megaqc-upload --no-ai --ignore-symlinks \
  -m fastqc --require-logs --outdir <new-empty-multiqc-output-dir> \
  <sample_fastqc.zip> [additional-explicit-fastqc-reports]
```

Do not pass a broad directory or `--force`. The network-disabling flags prevent
version checks, MegaQC upload, and AI features. Confirm that every expected
sample appears once; duplicate internal sample names or missing reports make the
result `partial` or `needs-decision`.

## File, privacy, and scale boundary

Operate only on a small, explicitly listed local set. Do not recurse, download,
upload, expose read sequences, reveal private paths, mutate inputs, or overwrite
artifacts. Large or batch inputs require separate resource planning and remain
outside this package. No remote adapter or credential is supported.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: FastQC requires an external Java application and real sequencing inputs; MultiQC is another external application. Complex-tool and batch execution were deliberately skipped for this instruction-only preview.
- Relevant versions: FastQC 0.12.1; MultiQC 1.35
- Unverified boundaries:
  - Agent routing and interactive behavior have not been runtime-evaluated
  - Scientific benchmark performance and human-expert review have not been established
  - FastQC report generation, archive parsing, and MultiQC aggregation were not executed
  - Large or batch FASTQ inputs and assay-, platform-, and library-specific expectations were not runtime-evaluated

A skipped path is not a pass. The exact package remains `preview + reviewed`.
