# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`evidence-synthesis-and-research-traceability`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Accept only a frozen corpus with a retrieval record and stable identifiers; if absent, return a retrieval handoff and do not search silently
- Map each material claim to sources at appropriate granularity and preserve support, conflict, uncertainty, and missing evidence
- Declare the evidence hierarchy and risk-of-bias framework before weighting claims
- Use PRISMA only when the task is actually a systematic review; reporting compliance is not scientific validation

## Optional adapters

- `PRISMA`
- `Cochrane Handbook`
- `Crossref REST`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| PRISMA | PRISMA 2020 | [PRISMA 2020 reporting guidance](https://www.prisma-statement.org/prisma-2020) | 2026-08-08 |
| Cochrane Handbook | 6.5.1 with 2025 revisions | [evidence-synthesis method reference](https://training.cochrane.org/versions-and-changes-handbook) | 2026-08-08 |
| Crossref REST | API v1 | [optional DOI metadata resolution](https://www.crossref.org/documentation/retrieve-metadata/api-versioning/) | 2026-08-08 |

## Network and data boundary

The core is offline. Optional DOI or PMID metadata correction sends only stable identifiers; never send private notes, unpublished conclusions, or the full corpus without separate authorization.

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

- Mode: `not-performed`
- Reason: The core is an instruction-only synthesis contract over a frozen corpus; no automated full-text, bias, citation-graph, or meta-analysis runtime is bundled.
- Relevant versions: PRISMA 2020, Cochrane Handbook 6.5.1, Crossref REST v1 optional
- Unverified boundaries:
  - Full-text OCR, large citation graphs, automated risk-of-bias judgments, and complex meta-analysis have not been evaluated
  - The package does not establish scientific validity of the frozen corpus or its included studies

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
