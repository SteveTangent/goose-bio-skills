# Runtime and scientific boundaries

This reference defines the operating boundary for
`raw-read-trimming-and-filtering` version `0.7.0`. Interfaces were reviewed
from official documentation on 2026-08-10; neither tool was executed.

## Scientific contract

- Use adapter identity, orientation, and matching semantics supported by library-preparation metadata. An inferred or automatically detected adapter is a declared policy choice, not ground truth.
- Quality, minimum-length, N-base, and paired-filter settings change the retained population. Justify them against the assay and downstream method; there is no universal safe threshold.
- Keep paired mates synchronized and label every count as reads or read pairs. Retention alone does not establish sample quality or successful removal of all unwanted sequence.
- Select exactly one tool per run. Do not compare or combine Cutadapt and fastp outputs unless a separate evaluation is explicitly requested.

## Reviewed local interfaces

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Cutadapt | 5.2; explicit single- or two-file paired FASTQ trimming/filtering and JSON report | [user guide](https://cutadapt.readthedocs.io/en/v5.2/guide.html), [changelog](https://cutadapt.readthedocs.io/en/v5.2/changes.html) | 2026-08-10 |
| fastp | 1.3.3; explicit single- or two-file paired FASTQ preprocessing with JSON/HTML reports and overwrite refusal | [official repository and usage](https://github.com/OpenGene/fastp), [v1.3.3 release](https://github.com/OpenGene/fastp/releases/tag/v1.3.3) | 2026-08-10 |

These are unverified compatibility surfaces, not bundled dependencies. Record
the exact installed version and help output before execution; do not install or
upgrade either tool silently.

## Command boundary

Use only explicitly listed inputs. Atomically create a user-approved new output
directory and stop if it already exists; all outputs below must remain inside
that directory. Replace placeholders only after recording the approved policy.

Cutadapt is primary when adapter matching is explicit. For paired reads, process
both mates together so pairing checks and filtering remain synchronized:

```text
cutadapt --version
cutadapt --cores 1 -a <R1-adapter> -A <R2-adapter> \
  <approved-quality-length-N-and-pair-filter-options> \
  --json <new-output-dir>/<sample>.cutadapt.json \
  -o <new-output-dir>/<sample>.trimmed.R1.fastq.gz \
  -p <new-output-dir>/<sample>.trimmed.R2.fastq.gz \
  <input-R1.fastq.gz> <input-R2.fastq.gz>
```

For single-end input, omit `-A`, `-p`, and paired-filter options. State whether
quality trimming is disabled or represented by `-q`; state minimum-length and
N-base policy rather than accepting an implicit scientific choice. Cutadapt has
no reviewed overwrite-refusal switch here, so never point it at a pre-existing
or reused directory.

fastp is an alternative only when its full effective policy is approved. Make
its report names explicit and use its overwrite guard:

```text
fastp --version
fastp --dont_overwrite --thread 1 \
  -i <input-R1.fastq.gz> -I <input-R2.fastq.gz> \
  -o <new-output-dir>/<sample>.trimmed.R1.fastq.gz \
  -O <new-output-dir>/<sample>.trimmed.R2.fastq.gz \
  --json <new-output-dir>/<sample>.fastp.json \
  --html <new-output-dir>/<sample>.fastp.html \
  <explicit-approved-adapter-quality-length-and-N-options>
```

For single-end input, omit `-I` and `-O`. Explicitly enable, disable, or set
adapter, quality, and length behavior because fastp supplies defaults. Do not
enable UMI, deduplication, merge, split, interleaved, failed-read, or stdout
modes in this package.

## Completion checks

Require a zero exit status, expected non-empty reports and FASTQ files, valid
FASTQ structure, output record counts that reconcile with the tool report, and
equal synchronized mate counts. Record input/output SHA-256 hashes, exact
command and version, adapter provenance, policy, processed and retained units,
retention percentage, discard reasons available in the report, warnings, and
limitations. A failed or interrupted run is `partial`; preserve and label any
new artifacts as incomplete rather than claiming completion.

## File, privacy, and scale boundary

Operate only on a small explicit local set. Do not recurse, download, upload,
expose read sequences, reveal private paths, mutate inputs, or overwrite
artifacts. When a quality-score operation is enabled, unresolved encoding is
`needs-decision`; unsupported encoding or long-read data is `needs-tool`.
Large or batch inputs require separate resource planning. No remote adapter or
credential is supported.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Cutadapt and fastp are external applications that create sequencing outputs; complex-tool execution and scientific output evaluation were deliberately skipped for this instruction-only preview.
- Relevant versions: Cutadapt 5.2; fastp 1.3.3
- Unverified boundaries:
  - Agent routing and interactive behavior have not been runtime-evaluated
  - Scientific benchmark performance and human-expert review have not been established
  - Cutadapt and fastp execution, FASTQ output validation, and report reconciliation were not executed
  - Large or batch inputs, interleaved reads, long reads, unusual quality encodings, and assay-specific policies were not runtime-evaluated

A skipped path is not a pass. The exact package remains `preview + reviewed`.
