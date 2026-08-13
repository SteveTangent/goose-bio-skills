# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`count-based-differential-expression`. The table records each interface's
freshness date; it does not claim that the tools were installed or runtime-tested
in this preview.

## Scientific contract

- Require raw counts or a declared transcript-estimate import contract, sample alignment, biological replication, and an estimable full-rank design
- Declare the exact contrast, filtering, normalization, outlier, shrinkage, and multiplicity policy
- Choose one modeling adapter and record its complete package/runtime combination
- Do not implement a simplified substitute model or treat quantifiers such as STAR, Salmon, or Kallisto as this Skill's executor

## Optional adapters

- `Bioconductor`
- `DESeq2`
- `edgeR`
- `tximport`
- `PyDESeq2`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.
For a future edgeR adapter, use the current `normLibSizes` name;
`calcNormFactors` is a legacy alias that emits a rename notice.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Bioconductor | Bioconductor 3.23 with R 4.6 | [R/Bioconductor release contract](https://bioconductor.org/about/release-announcements/) | 2026-08-08 |
| DESeq2 | 1.52.0 | [negative-binomial count differential expression](https://bioconductor.org/packages/release/bioc/html/DESeq2.html) | 2026-08-08 |
| edgeR | 4.10.3 | [negative-binomial count differential expression](https://bioconductor.org/packages/release/bioc/html/edgeR.html) | 2026-08-13 |
| tximport | 1.40.0 | [transcript-estimate import contract](https://bioconductor.org/packages/release/bioc/html/tximport.html) | 2026-08-08 |
| PyDESeq2 | 0.5.4 | [independent Python DESeq2-style implementation](https://pydeseq2.readthedocs.io/en/stable/) | 2026-08-08 |

## Network and data boundary

Package installation may require network access. Once installed, local count and metadata analysis is offline; no sample data should be uploaded by the core Skill.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: R/Bioconductor and PyDESeq2 model fitting, dependency installation, and dataset-scale diagnostics were not run for this preview.
- Relevant versions: Bioconductor 3.23 / R 4.6, DESeq2 1.52.0, edgeR 4.10.3, tximport 1.40.0, PyDESeq2 0.5.4
- Unverified boundaries:
  - No negative-binomial model, shrinkage, outlier, or diagnostic workflow was executed
  - DESeq2, edgeR, and PyDESeq2 numerical results are not claimed to be interchangeable

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
