# Runtime and scientific boundaries

This reference defines the operating boundary for
`proteomics-quantification-table-qc` version `0.6.0`.

## Scientific contract

- Accept only an already quantified peptide-, protein-group-, or protein-level table with an explicit row boundary and sample design.
- Keep missing, zero, negative, censored, filtered, and below-detection values distinct until export semantics are documented.
- Separate data-readiness findings from normalization, imputation, batch correction, statistical modeling, and biological interpretation.
- Treat sample outlier signals as review prompts, not automatic exclusion decisions.
- Preserve feature and sample provenance; never infer identification or protein-inference quality from abundance values alone.

## Optional local interfaces

The first release is instruction-only. QFeatures and MSstats are reviewed
downstream compatibility surfaces, not bundled dependencies and not evidence
that an R workflow ran.

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Bioconductor | 3.23 with R 4.6 | [Bioconductor release announcements](https://bioconductor.org/about/release-announcements/) | 2026-08-09 |
| QFeatures | 1.22.0 | [QFeatures package](https://bioconductor.org/packages/QFeatures/) | 2026-08-09 |
| MSstats | 4.20.0; downstream modeling only | [MSstats package](https://bioconductor.org/packages/MSstats/) | 2026-08-09 |

## File and data boundary

An explicit safe local QC request authorizes bounded reads of the declared table
and sample metadata and creation of one requested new report. No duplicate
confirmation is required while the paths, scope, and non-mutating action remain
unchanged.

Do not recurse through directories, upload data, use the network, mutate source
tables, or overwrite an artifact. Inspect schema and a bounded sample before a
full scan. If file size, object format, memory needs, or required tooling exceed
the host's bounded capability, return `partial` or `needs-tool` and record the
skipped checks. `scientific-file-preflight-and-resource-planning` owns file-size
and resource preflight; it does not replace proteomics-specific QC.

## Scope exclusions

- Raw spectra conversion, peak processing, database search, PSM scoring, PEP/q-value/FDR, and protein inference are outside this package.
- Normalization, imputation, differential abundance, multiplicity correction, pathway analysis, and clinical interpretation are downstream decisions.
- PSM, peptide, protein-group, and protein levels must not be combined into one QC population.
- Vendor-specific export conventions are not assumed from filenames or column labels alone.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Large-table and R/Bioconductor execution require complex tools and were deliberately skipped for this instruction-only release
- Relevant versions: Bioconductor 3.23 with R 4.6, QFeatures 1.22.0, MSstats 4.20.0
- Unverified boundaries:
  - Agent routing and interactive behavior have not been runtime-evaluated
  - Scientific benchmark performance and human-expert review have not been established
  - Large quantification tables, vendor-specific exports, and complex quantitative objects have not been runtime-evaluated
  - No normalization, imputation, batch correction, statistical model, or downstream multiplicity procedure was run

A skipped complex-tool path is not a pass. The package remains
`preview + reviewed`.
