# Provenance and sanitization policy

## Principle

Sanitization protects private research context; it does not erase authorship, licenses, or the fact that ideas have provenance.

## Private evidence retained in `skill-research`

- source repository URL and immutable commit
- file, symbol, and line anchors
- raw comparison notes and community excerpts
- source-to-capability and source-to-release mappings
- rejected patterns and reviewer reasoning
- license analysis and approval record

## Content allowed in `02-bio-skills`

- newly written, verified instructions
- public official or scientific citations needed to support recommendations
- legally required copyright, license, and attribution notices
- aggregate or opaque internal provenance IDs that cannot reveal private source identities
- release date, freshness date, owner, status, and review cadence

## Content removed before export

- private URLs, usernames, issue identifiers, local paths, and private discussion text
- copied phrasing not needed or not licensed for redistribution
- source rankings, unreviewed allegations, and reversible stylistic fingerprints
- secrets, protected data, raw prompts containing private context, and environment-specific credentials

## Release rule

Every released Skill version must have a private export record linking it to source commits, evidence, license decisions, eval results, sanitizer result, reviewer, and rollback target.

If legal attribution would reveal a source the project is unwilling to disclose, the material cannot be used. It must not be “anonymized” around the license requirement.
