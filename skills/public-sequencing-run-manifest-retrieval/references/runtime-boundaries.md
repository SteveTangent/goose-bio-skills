# Runtime and scientific boundaries

This reference defines the operating boundary for
`public-sequencing-run-manifest-retrieval` version `0.5.0`. Interfaces were
reviewed on 2026-08-10; this preview does not claim exact-package runtime
evaluation.

## Scientific contract

- Accept existing public INSDC study, experiment, sample, BioProject, BioSample, or run accessions; reject keywords, wildcards, and free-form search expressions.
- Treat a run as the file manifest linked to its experiment and sample, not as proof that the sample or experiment suits a scientific question.
- Preserve provider-reported study, experiment, sample, run, layout, platform, model, file role, URL, byte count, and MD5 values.
- Parse returned columns by header name rather than assumed order. Keep every multi-file URL, byte, MD5, and role value positionally coupled; a cardinality mismatch is `partial`, never a guessed pairing.
- Default to generated FASTQ fields. Use submitted-file or SRA-archive fields only when the user explicitly requests that representation.
- Keep discovery, reads download, local checksum recomputation, QC, conversion, alignment, and bulk harvesting outside this Skill.

## Shared live read-only adapter

The Skill uses `ena-portal-api` through the repository shared connector for
anonymous `GET` or `HEAD` access to exactly:

`https://www.ebi.ac.uk/ena/portal/api/filereport`

Use `result=read_run`, `format=tsv`, one exact accession, and one reviewed field
set per request. The common fields are `study_accession`,
`experiment_accession`, `sample_accession`, `run_accession`, `library_layout`,
`instrument_platform`, and `instrument_model`. Append exactly one matched
quartet: `fastq_file_role`, `fastq_ftp`, `fastq_bytes`, `fastq_md5`;
`submitted_file_role`, `submitted_ftp`, `submitted_bytes`, `submitted_md5`; or
`sra_file_role`, `sra_ftp`, `sra_bytes`, `sra_md5`.

The endpoint may accept study (`ERP`, `SRP`, `DRP`, `PRJ`), experiment (`ERX`,
`SRX`, `DRX`), sample (`ERS`, `SRS`, `DRS`, `SAM`), and run (`ERR`, `SRR`,
`DRR`) accessions for `read_run`. Submission and analysis accessions are outside
this Skill.

## Interface freshness

| Component | Reviewed interface | Official documentation | Checked |
| --- | --- | --- | --- |
| ENA Portal API | rolling `filereport`; `read_run` return fields | [File reports](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html), [programmatic access and rate limit](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access.html), and [live `read_run` return fields](https://www.ebi.ac.uk/ena/portal/api/returnFields?result=read_run) | 2026-08-10 |
| NCBI SRA metadata model | public Study/Sample/Experiment/Run relations | [SRA metadata overview](https://www.ncbi.nlm.nih.gov/sra/docs/submitmeta/) and [RunInfo guidance](https://www.ncbi.nlm.nih.gov/sra/docs/sradownload/) | 2026-08-10 |
| Bio 02 shared connector | `0.5.0` public read-only contract | repository connector contract | 2026-08-10 |

NCBI documentation is used for the shared INSDC/SRA object model; this Skill's
live provider is ENA, not an undocumented NCBI RunInfo endpoint.

## Network and data boundary

The user's explicit request for a small public accession manifest authorizes
the targeted anonymous read. No provider configuration or credential prompt is
needed. Send only one exact accession, `result`, `format`, and the fixed field
list. Never send free text, patient identifiers, private accessions, embargoed
metadata, controlled-access identifiers, credentials, or arbitrary query
parameters.

The provider documents an upper service limit of 50 requests per second; the
shared catalog uses a conservative 2 requests per second. The Skill is
stricter: at most five accessions, five requests, 100 returned runs, 1 MiB per
response, and 4 MiB total accepted response bytes. Pass `--max-bytes 1048576`.
Stop on 429, truncation, unexpected headers, malformed multi-file cardinality,
or any limit breach; do not silently search, paginate, or download reads.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Network transport follows the agent host's proxy and CA trust policy. On a
missing adapter, provider failure, not-found or suppressed record, truncation,
or oversized project expansion, return `needs-tool`, `partial`, or
`needs-decision` honestly. A provider-reported MD5 becomes an integrity result
only after a separate authorized download and local recomputation, both outside
this Skill.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Exact-package multi-accession routing, large project expansion, read downloads, and batch retrieval were not run; downloads and bulk paths are excluded rather than treated as passed.
- Relevant interfaces: ENA Portal API rolling `filereport` and `returnFields`, NCBI SRA public metadata model, Bio 02 shared connector 0.5.0 contract.
- Unverified boundaries:
  - Exact-package accession validation, connector routing, TSV header parsing, and semicolon-delimited file-field alignment have not been runtime-evaluated.
  - Large study or BioProject expansion, withdrawn or suppressed accessions, empty file fields, rate limiting, and oversized responses remain unverified.
  - Reads download, local integrity recomputation, study discovery, QC, and bulk harvesting are outside this preview.

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
