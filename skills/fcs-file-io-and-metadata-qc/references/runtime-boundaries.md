# Runtime and scientific boundaries

This reference defines the operating boundary for
`fcs-file-io-and-metadata-qc` version `0.6.0`.

## Scientific contract

- Treat FCS structure and metadata QC as file-readiness evidence, not as evidence that compensation, gating, acquisition, or the experiment is scientifically valid.
- Preserve dataset and parameter order. Keep detector names (`$PnN`) distinct from stain or marker descriptions (`$PnS`).
- Report `$PnE`, `$PnG`, and `$PnR` as declared scaling metadata; do not infer transformed or compensated values from these fields alone.
- A spillover keyword means a matrix was declared. It does not prove that the matrix is correct or that compensation was applied.
- Metadata can contain operator, sample, subject, or instrument identifiers. Emit a reviewed summary by default; unrestricted TEXT or ANALYSIS export is outside the default boundary.

## Reviewed local interface

The first release is instruction-only. FlowIO is a reviewed optional adapter,
not a bundled dependency and not evidence that a representative FCS file was
executed.

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| FlowIO | 1.4.0; `FlowData`, metadata-first `only_text=True`, FCS 2.0/3.0/3.1 | [FlowIO API](https://flowio.readthedocs.io/en/latest/api.html) | 2026-08-10 |
| FlowIO tutorial | 1.4.0; sections, metadata, channels, and datasets | [FlowIO tutorial](https://flowio.readthedocs.io/en/latest/notebooks/flowio_tutorial.html) | 2026-08-10 |
| FCS standard | FCS 3.1 normative structure and required keywords | [FCS 3.1 publication and supplement](https://pmc.ncbi.nlm.nih.gov/articles/PMC2892967/) | 2026-08-10 |

FlowIO is distributed separately under the BSD 3-Clause License. No FlowIO or
FCS specification bytes are bundled in this package.

## File and resource boundary

An explicit safe local inspection request authorizes bounded reads of named
regular files and creation of one requested new report. Do not recurse through
directories, follow symlinks, upload data, mutate inputs, or overwrite output.

Start with file size and metadata-only parsing. FlowIO can load event data into
memory, and conversion to an array can allocate additional memory. Before any
event statistics, estimate at least `event_count × channel_count × 8` bytes,
add adapter overhead, and apply the user or host limit. If the estimate or file
count exceeds the bound, return `partial` or `needs-tool`.

Offset-repair or discrepancy-tolerance options change parser behavior. They may
be used only when explicitly reported, and their warnings remain visible. Do
not silently accept malformed offsets.

## Scope exclusions

- Compensation, transformation, gating, clustering, downsampling, concatenation, and population statistics are outside this package.
- FlowJo workspace, GatingML, instrument-control, and acquisition-QC workflows are outside this package.
- Full event export, FCS rewriting, de-identification, and format conversion are outside this package.
- Marker interpretation, cell-type annotation, diagnosis, treatment, and other clinical use are prohibited.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: FlowIO and representative FCS fixtures were not installed or run for this instruction-only release
- Relevant versions: FlowIO 1.4.0; FCS 3.1
- Unverified boundaries:
  - Agent routing and interactive behavior have not been runtime-evaluated
  - Scientific benchmark performance and human-expert review have not been established
  - FCS 2.0/3.0/3.1 fixtures, multiple datasets, malformed offsets, and large-file behavior were not executed
  - No compensation, transformation, gating, clustering, workspace import, event export, or clinical workflow was run

A skipped complex-tool path is not a pass. The package remains
`preview + reviewed`.
