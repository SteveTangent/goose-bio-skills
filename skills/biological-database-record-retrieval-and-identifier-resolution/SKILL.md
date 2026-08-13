---
name: biological-database-record-retrieval-and-identifier-resolution
description: "Retrieve bounded public gene, transcript, protein, or nucleotide records from UniProt, Ensembl, or NCBI. Preserve provider provenance and mapping ambiguity. Exclude syntax checks, literature, homology, structures, chemistry, bulk mapping, and clinical use."
license: Apache-2.0
metadata:
  version: "0.8.0"
---

# Biological Database Record Retrieval and Identifier Resolution

`Preview + reviewed`; runtime and expert review were not performed.

## Owns

Retrieve bounded public biological records and resolve declared namespaces
without forcing one canonical answer.

## Inputs

- bounded identifiers or query, source and target namespaces, and fields
- organism or taxon when a symbol or cross-reference is ambiguous
- output format and a new path when a file artifact is requested

## Intake

Inspect identifiers and scope first. An explicit public retrieval request
authorizes the bounded anonymous reads below; do not ask for configuration,
credentials, or a second confirmation. Ask one unresolved result-changing
question with a recommendation, then wait.

Decision order:

1. **taxon-boundary.** Which taxon constrains an unqualified symbol? Recommended: require a user-declared taxon.

## Public network execution

Use the shared read-only connector with `uniprot-rest`, `ensembl-rest`, or
`ncbi-eutils`. Choose the issuing authority from the namespace; never silently
fall back. Limit one invocation to 20 identifiers, 5 requests, and 16 MiB.
Paid providers, uploads, arbitrary URLs, remote writes, full downloads, and
asynchronous or bulk mapping are out of scope.

Pass `--max-bytes 16777216`. Count every HTTP response, including pagination,
toward the five-request limit; stop before a sixth.

## Workflow

1. Freeze namespaces, taxon, fields, and scope; reject unresolved authority.
2. Route UniProt, Ensembl, and NCBI identifiers to their issuing provider.
3. Run allowlisted anonymous reads and record outcomes.
4. Preserve source and canonical IDs, versions, mapping cardinality, status, exposed release metadata, and ambiguity.

## Output contract

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. `completed` includes:

- provider, endpoint class, redacted request URL and parameters, access time,
  request count, and response fingerprint
- requested and returned identifiers, versions, fields, and exposed release metadata
- mapping cardinality, deprecated/replaced/not-found states, assumptions, and omissions

Truncated, failed, or skipped retrieval is not `completed`. Never overwrite
inputs.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Cross-references
are provider assertions, not proof of biological equivalence.

## Guardrails

- Send only required public identifiers, terms, taxon, fields, and pagination.
- Preserve versions and every mapping; never collapse ambiguity silently.
- Route syntax, literature, homology, structure, and chemistry to their owning Skills.
- Keep sensitive, private, patient, unpublished, and controlled data out of public providers.
- Require researcher review; this Skill has no clinical authority.
