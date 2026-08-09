# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`sequence-similarity-and-homology-search`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Record query molecule type, engine and version, database release or digest, masking, E-value, coverage, hit cap, and all non-default parameters
- Use a micro database only for installation smoke, never for research interpretation
- For research execution require a question-appropriate complete or curated database fixed by release and digest
- Preserve normalized hits and the raw result artifact
- Do not infer orthology, function, or evolutionary mechanism from similarity alone
- Route downstream pairwise or multiple alignment to the alignment Skill

## Optional adapters

- `NCBI BLAST+`
- `MMseqs2`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| NCBI BLAST+ | 2.17.0 | [command-line local and remote similarity search](https://www.ncbi.nlm.nih.gov/books/NBK131777/) | 2026-08-08 |
| MMseqs2 | 18-8cc5c | [search and database workflow](https://github.com/soedinglab/MMseqs2/releases) | 2026-08-08 |

## Network and data boundary

Fixed local databases can be searched offline. Remote BLAST and database downloads require network access; disclose the provider, query sequence data, database release, and retrieval date.

Public status and bounded result downloads are authorized after the related job
submission is authorized. Confirm an unrequested bulk expansion, sensitive
upload, remote job, credential-required path, paid use, or non-default host.
Anonymous public access needs no provider configuration or optional API key.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-user-config`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Use the declared default public provider directly for the requested bounded
read or download. If a confirmation condition applies, disclose the exact
provider, data, scope, destination, credential and billing boundary first; do
not reconfirm an exact action already authorized by the current request, except
for sensitive data. On missing adapters, unavailable network, provider failure,
truncation, or missing authorization, degrade honestly and never claim a call.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Full reference databases, indexing, remote live databases, GPU/MPI execution, and large searches were not staged for this preview.
- Relevant versions: NCBI BLAST+ 2.17.0, MMseqs2 18-8cc5c, reference databases not-detected
- Unverified boundaries:
  - NR, NT, UniRef, and other full-database downloads and indexes have not been built or searched
  - Remote BLAST, GPU, MPI, and large-scale result stability have not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
