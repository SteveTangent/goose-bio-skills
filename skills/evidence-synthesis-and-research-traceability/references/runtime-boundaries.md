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

The core is offline. Optional DOI metadata correction uses anonymous Crossref
public access and sends only stable identifiers. The shared adapter does not
accept contact or credential values; never send private notes or unpublished
conclusions, or fall back to a paid provider.

The user's explicit citation-resolution request authorizes targeted public DOI
metadata reads and bounded responses. Anonymous access requires no provider
configuration or API key. Confirm only an unrequested bulk expansion, sensitive
upload, remote job, or non-default host.

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

- Mode: `not-performed`
- Reason: The core is an instruction-only synthesis contract over a frozen corpus; no automated full-text, bias, citation-graph, or meta-analysis runtime is bundled.
- Relevant versions: PRISMA 2020, Cochrane Handbook 6.5.1, Crossref REST v1 optional
- Unverified boundaries:
  - Full-text OCR, large citation graphs, automated risk-of-bias judgments, and complex meta-analysis have not been evaluated
  - The package does not establish scientific validity of the frozen corpus or its included studies

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
