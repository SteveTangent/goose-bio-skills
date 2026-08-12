---
name: public-sequencing-run-manifest-retrieval
description: "Retrieve a bounded public sequencing run/file manifest for exact INSDC study, experiment, sample, BioProject, BioSample, or run accessions; narrow over-limit exact-accession requests before execution. Return linked IDs, layout, platform, file URLs, bytes, and MD5. Exclude discovery, read downloads, QC, conversion, alignment, and bulk harvesting."
license: Apache-2.0
metadata:
  version: "0.7.0"
---

# Public Sequencing Run Manifest Retrieval

`Preview + reviewed`; runtime and expert review were not performed.

## Owns

Turn public INSDC accessions into a bounded run/file manifest, not a search.

## Inputs

- up to five exact public accessions of the supported INSDC classes
- generated FASTQ by default; submitted or SRA files only when requested
- a new output path when a file artifact is requested

## Intake

Inspect syntax, count, representation, and output path first. An explicit
bounded lookup authorizes anonymous read. Ask one unresolved result-changing
question with a recommendation, then wait.

Decision order:

1. **manifest-scope.** Which exact accessions bound this manifest? Recommended: provide at most five run, experiment, or sample accessions expected to yield no more than 100 runs.

## Public network execution

Use `ena-portal-api` at exact `filereport` with `result=read_run`, `format=tsv`,
and fixed fields. Limits: 1 MiB per request; five requests, 100 runs, and 4 MiB
accepted per invocation.

## Workflow

1. Validate accession class; freeze scope and representation.
2. Request identifiers, layout, platform, model, role, URL, bytes, and MD5.
3. Parse by header; keep semicolon-delimited role, URL, byte, and MD5 values positionally coupled.
4. Preserve empty, withdrawn, suppressed, and not-found states. On a limit breach, request narrower accessions.
5. Deduplicate rows while retaining request links and response fingerprints.

## Output contract

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. `completed` includes:

- accession links, run, layout, platform, and instrument model
- representation, role, provider URL, bytes, checksum algorithm, and checksum
- provider, redacted request, access time, counts, fingerprint, gaps, and assumptions

Every accession must resolve within limits. URLs do not prove availability;
reported MD5 values are not local integrity checks. Never overwrite files.

## Runtime and scientific boundaries

Read [runtime boundaries](references/runtime-boundaries.md). Require researcher
review of sample identity and suitability.

## Guardrails

- Send only exact public accessions and fixed report fields.
- Keep patient, private, embargoed, controlled, and credential-bearing data out of the provider.
- Do not discover, download reads, verify integrity, run QC, convert, align, or harvest in bulk.
- Never infer pairing from filename alone; preserve provider layout and file-role fields.
- Do not claim clinical, diagnostic, or therapeutic authority.
