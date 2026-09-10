# Working rules for Goose Bio Skills

## Mission

Maintain a small, trustworthy library of installable bioinformatics agent Skills. This repository is the source-clean output boundary, not the research workspace or the place where upstream code is collected.

## Admission rules

- Accept a Skill only through a reviewed, license-cleared export from a private research package.
- Require one recurring job, explicit inputs and outputs, exclusions, failure handling, and human-judgment boundaries.
- Follow the Agent Skills specification: directory name equals frontmatter `name`; `name` and `description` are valid; `SKILL.md` is concise; optional resources are referenced and necessary.
- Keep platform-neutral meaning in the Skill. Add platform adapters only when bounded, explicit, and either tested or marked unverified.
- Require an owner, version, review cadence, last scientific/tool freshness check, release stage, and assurance level.

## Two-axis lifecycle

- `release_stage` is `preview` or `stable`.
- `assurance_level` is `reviewed` or `evaluated`.
- `preview + reviewed`, `preview + evaluated`, and `stable + evaluated` are valid installable states. `stable + reviewed` is invalid.
- `reviewed` means the exact package passed source, scientific-contract, rights, dependency, safety, sanitization, and static package review. It does not mean runtime validation or superiority over a baseline.
- Human expert review may be `not-performed` for preview admission and must be stated explicitly when absent.
- `evaluated` means a bounded evaluation of the exact package is recorded. It does not imply universal scientific validity.
- A `preview` Skill must never claim to be validated, proven better, or better than a no-Skill baseline.

## Pre-execution interaction contract

- Inspect safely discoverable facts first.
- Ask one focused question for the most consequential unresolved fact or choice. Explain why it matters and request the minimum useful record; related fields may use one compact table. Wait on dependent work. Explain unfamiliar terms, flag evidence-backed misconceptions, and never guess biological facts. With complete inputs, proceed.
- If the current request already authorizes safe local, non-destructive execution and the scope is unchanged, proceed without a shared-understanding confirmation or a second execution confirmation.
- Ask one scoped authorization question only for a new material side effect that is not already explicitly authorized for the current action and scope.
- Keep the core provider-neutral. External adapters must be optional, explicit, tested or marked unverified, and free of advertising or sign-up funnels.

## Privacy, provenance, and licensing

- Do not include private source records, raw source URLs, usernames, local paths, private issue excerpts, or reversible source fingerprints.
- Do not include upstream repository credits, source labels, private provenance IDs, or source watermarks in the core Skill package.
- Leave publication credits and any unified cover watermark to the project owner’s later cover/release layer.
- Never include secrets, patient data, protected health information, or controlled-access datasets.
- Do not copy source prose unless its license and attribution are explicitly reviewed.
- Never copy an upstream script verbatim into this repository. Evaluate the upstream behavior privately, then write an original, reviewed implementation that improves, optimizes, or safely narrows it.
- Preserve all legally required copyright notices, license text, and attribution. Sanitization cannot be used to conceal derivation.
- Never remove a third-party watermark for reuse; exclude the asset or replace it with an original asset.
- Keep the complete source ledger, private release mapping, and future publication-credit bundle in the private research archive only.

## Scientific and safety quality

- Verify time-sensitive tool, package, API, and database instructions against official sources.
- State assay, organism, reference-build, input-format, and experimental-design assumptions when they change the recommendation.
- Do not convert forum popularity into scientific recommendation.
- Do not claim clinical, diagnostic, or therapeutic authority.
- Require the user to inspect QC and biological plausibility at decision points that cannot be safely automated.

## Verification before completion

Choose checks by the changed behavior: package edits require structure, source
and affected helper checks; shared validator or execution changes require their
regressions. Use the full retained replay set for release preparation or changes
that affect that set. Once relevant checks pass, do not repeat or expand them
without a new change, failure or unresolved concern. These completion rules do
not weaken the admission, privacy, input-validation or no-overwrite boundaries.

- Validate Skill structure and frontmatter.
- Review trigger positives, negatives, and near-neighbor cases statically; execute them only when the declared assurance includes that bounded evaluation.
- Every bundled script must provide and pass one deterministic self-test; small scripts cannot use a skip to bypass it.
- Batch-scale, GPU-bound, or complex external-tool runtime testing is separate from script self-testing and may be recorded as `skipped-complex-tool`, with its reason, relevant tool versions, and every resulting unverified boundary.
- Do not describe a skipped path as evaluated. For `stable`, skipped behavior must remain outside the stable assurance claim.
- Scan for secrets, private identifiers, upstream source presentation, stale interfaces, unsafe commands, and missing legally required notices.
- Inspect the Git diff and rebuild the local code graph after meaningful code changes.
