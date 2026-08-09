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

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

### External service gate

- `disclosure`: `provider-purpose-would_send-credential-billing`
- `confirmation`: `two-stage-exact-token`
- `config_access`: `after-exact-token-only`
- `companion_mode`: `zero-network-plan-only`
- `standalone_fallback`: `needs-user-config-or-needs-tool`
- `call_claim`: `forbidden-before-live-execution`

Before any external-service call, disclose the catalog provider ID, purpose,
`would_send` fields, credential requirements, and billing or quota terms. With
the repository companion, stage 1 runs root `scripts/check_research_connectors.py`
with provider IDs only and no config path; it emits a `confirmation_token`
without touching user config. Stage 2 may read config and produce a zero-network
plan only after the user returns that exact token; neither stage calls a provider.
For a standalone install or missing user configuration, fail closed with
`needs-user-config` or `needs-tool`; never claim that the service was called.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Large multiple alignments, hosted service jobs, and long-running strategy comparisons were not executed for this preview.
- Relevant versions: Biopython 1.87, MAFFT 7.526, EMBL-EBI Clustal Omega job version not-run
- Unverified boundaries:
  - Large MSA, multi-day jobs, hosted-service results, and strategy sensitivity have not been runtime-tested
  - Cross-engine alignment equivalence is not established

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
