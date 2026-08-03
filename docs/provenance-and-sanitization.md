# Source separation and sanitization policy

## Principle

Complete provenance belongs in private `skill-research`. The installable `02-bio-skills` core is intentionally source-clean: it does not display upstream repository credits, source labels, source watermarks, or private provenance IDs. The project owner may add one consistent source and credit treatment later in the publication cover/release layer.

## Private evidence retained in `skill-research`

- source repository URL and immutable commit
- file, symbol, and line anchors
- raw comparison notes and community excerpts
- source-to-capability and source-to-release mappings
- rejected patterns and reviewer reasoning
- license analysis and approval record
- a publication-credit bundle prepared for the owner’s future cover or release page

## Content allowed in `02-bio-skills`

- newly written, verified instructions
- legally required copyright, license, and attribution notices
- release date, freshness date, owner, status, and review cadence
- scientific citations only when they are required for correct runtime behavior or explicitly part of the Skill’s output contract

## Content removed before export

- private URLs, usernames, issue identifiers, local paths, and private discussion text
- upstream source credits, source labels, source watermarks, and private or opaque provenance IDs
- copied phrasing not needed or not licensed for redistribution
- source rankings, unreviewed allegations, and reversible stylistic fingerprints
- secrets, protected data, raw prompts containing private context, and environment-specific credentials

## Release rule

Every released Skill version must have a private export record linking it to source commits, evidence, license decisions, eval results, sanitizer result, reviewer, and rollback target.

The source list prepared from that record stays private until the project owner intentionally adds it to a publication cover, release page, or other wrapper. The core Skill must not add its own credit block or watermark.

Do not erase a third-party watermark to make an asset appear source-clean. Exclude that asset or create a genuinely original replacement.

If legally required attribution would reveal a source the project is unwilling to disclose, the material cannot be used in the clean core. It must not be “anonymized” or deferred to an optional cover around the license requirement.
