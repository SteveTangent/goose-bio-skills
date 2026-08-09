# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`pairwise-and-multiple-sequence-alignment`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Separate pairwise from multiple alignment and declare nucleotide or protein input
- Declare global or local objective, scoring matrix, gap penalties, strategy, threads, seed if present, and input order
- Report low-confidence or strategy-sensitive regions rather than treating one alignment as ground truth
- Route database search to the similarity-search Skill

## Optional adapters

- `Biopython`
- `MAFFT`
- `EMBL-EBI Clustal Omega`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Biopython | 1.87 | [Bio.Align PairwiseAligner](https://biopython.org/docs/1.87/api/Bio.Align.html) | 2026-08-08 |
| MAFFT | 7.526 | [multiple sequence alignment CLI](https://mafft.cbrc.jp/alignment/software/index.html) | 2026-08-08 |
| EMBL-EBI Clustal Omega | record the version returned by each job | [job-specific hosted alignment service](https://www.ebi.ac.uk/jdispatcher/docs/faqs/clustal/) | 2026-08-08 |

## Network and data boundary

Biopython and MAFFT are local and offline. Hosted Clustal Omega uploads sequence data and requires explicit authorization plus the exact service version returned with the job.

Public status and bounded result downloads are authorized after the related job
submission is authorized. Confirm an unrequested bulk expansion, sensitive
upload, remote job, credential-required path, paid use, or non-default host.
Anonymous public access needs no provider configuration or optional API key.

### External service gate

- `public_access`: `explicit-request-authorizes-bounded-read-download`
- `confirmation`: `sensitive-upload-remote-job-bulk-or-paid`
- `config_access`: `shared-companion-reads-no-provider-config-or-credentials`
- `credential_policy`: `shared-companion-anonymous-only`
- `standalone_fallback`: `needs-tool-dry-run-or-partial`
- `call_claim`: `only-after-checked-live-response`

Network transport follows the agent host's proxy and CA trust policy; the
shared companion does not read provider configuration or credentials.

Use the declared default public provider directly for the requested bounded
read or download. If a confirmation condition applies, disclose the exact
provider, data, scope, destination, credential and billing boundary first; do
not reconfirm an exact action already authorized by the current request, except
for sensitive data. On missing adapters, unavailable network, provider failure,
truncation, or missing authorization, degrade honestly and never claim a call.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Large multiple alignments, hosted service jobs, and long-running strategy comparisons were not executed for this preview.
- Relevant versions: Biopython 1.87, MAFFT 7.526, EMBL-EBI Clustal Omega job version not-run
- Unverified boundaries:
  - Large MSA, multi-day jobs, hosted-service results, and strategy sensitivity have not been runtime-tested
  - Cross-engine alignment equivalence is not established

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
