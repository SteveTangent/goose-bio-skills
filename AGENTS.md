# Working rules for 02-bio-skills

## Mission

Maintain a small, trustworthy library of installable bioinformatics agent Skills. This repository is the reviewed output boundary, not the research workspace.

## Admission rules

- Accept a Skill only through a reviewed export from `skill-research` or an equivalent evidence package.
- Require one recurring job, explicit inputs and outputs, exclusions, failure handling, and human-judgment boundaries.
- Follow the Agent Skills specification: directory name equals frontmatter `name`; `name` and `description` are valid; `SKILL.md` is concise; optional resources are referenced and necessary.
- Keep platform-neutral meaning in the Skill. Add platform adapters only when tested and semantically equivalent.
- Require an owner, version, review cadence, lifecycle state, and last scientific/tool freshness check.

## Privacy, provenance, and licensing

- Do not include private source records, raw source URLs, usernames, local paths, private issue excerpts, or reversible source fingerprints.
- Do not include upstream repository credits, source labels, private provenance IDs, or source watermarks in the core Skill package.
- Leave publication credits and any unified cover watermark to the project owner’s later cover/release layer.
- Never include secrets, patient data, protected health information, or controlled-access datasets.
- Do not copy source prose unless its license and attribution are explicitly reviewed.
- Preserve all legally required copyright notices, license text, and attribution. Sanitization cannot be used to conceal derivation.
- Never remove a third-party watermark for reuse; exclude the asset or replace it with an original asset.
- Keep the complete source ledger, private release mapping, and future publication-credit bundle in `skill-research` only.

## Scientific and safety quality

- Verify time-sensitive tool, package, API, and database instructions against official sources.
- State assay, organism, reference-build, input-format, and experimental-design assumptions when they change the recommendation.
- Do not convert forum popularity into scientific recommendation.
- Do not claim clinical, diagnostic, or therapeutic authority.
- Require the user to inspect QC and biological plausibility at decision points that cannot be safely automated.

## Verification before completion

- Validate Skill structure and frontmatter.
- Run trigger positives, negatives, and near-neighbor cases.
- Run the smallest representative output or file-backed fixture check.
- Scan for secrets, private identifiers, upstream source presentation, stale interfaces, unsafe commands, and missing legally required notices.
- Inspect the Git diff and rebuild the local code graph after meaningful code changes.
