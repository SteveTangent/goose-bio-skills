# Source separation and sanitization policy

## Principle

Complete provenance belongs in a separate private research archive. The installable `02-bio-skills` core is intentionally source-clean: it does not display upstream repository credits, source labels, source watermarks, or private provenance IDs. The project owner may add one consistent source and credit treatment later in the publication cover/release layer.

## Private evidence retained outside the distribution repository

- source repository URL and immutable commit
- file, symbol, and line anchors
- raw comparison notes and community excerpts
- source-to-capability and source-to-release mappings
- rejected patterns and reviewer reasoning
- license analysis and approval record
- a publication-credit bundle prepared for the owner’s future cover or release page

## Content allowed in `02-bio-skills`

- newly written, reviewed instructions
- original scripts written after private behavior evaluation and never copied verbatim from an upstream repository
- legally required copyright, license, and attribution notices
- release date, freshness date, owner, two-axis lifecycle state, review cadence, verification skips, and unverified boundaries
- scientific citations only when they are required for correct runtime behavior or explicitly part of the Skill’s output contract

## Content removed before export

- private URLs, usernames, issue identifiers, local paths, and private discussion text
- upstream source credits, source labels, source watermarks, and private or opaque provenance IDs
- copied phrasing not needed or not licensed for redistribution
- copied upstream scripts, even when the upstream license would otherwise permit redistribution
- source rankings, unreviewed allegations, and reversible stylistic fingerprints
- secrets, protected data, raw prompts containing private context, and environment-specific credentials

## Release rule

Every installable Skill version must have a private export record linking it to source commits, fusion and scientific-contract evidence, license decisions, assurance state, any bounded evaluation or declared skip, sanitizer result, reviewer, and rollback target.

The source list prepared from that record stays private until the project owner intentionally adds it to a publication cover, release page, or other wrapper. The core Skill must not add its own credit block or watermark.

Do not erase a third-party watermark to make an asset appear source-clean. Exclude that asset or create a genuinely original replacement.

Do not make an upstream script appear source-clean by renaming variables, reformatting it, or removing comments. Evaluate its behavior privately and implement the required capability anew, with a documented improvement, optimization, or safety narrowing. Every bundled implementation receives a deterministic self-test. A separate batch, GPU, or complex external-tool runtime test may be `skipped-complex-tool`; the public manifest then records the reason, relevant versions, and unverified boundary.

If legally required attribution would reveal a source the project is unwilling to disclose, the material cannot be used in the clean core. It must not be “anonymized” or deferred to an optional cover around the license requirement.

Sanitization never removes a required `LICENSE`, `NOTICE`, copyright, or attribution file. A preview package with no runtime evaluation must say so and must not use validated, proven-superior, or better-than-baseline claims.
