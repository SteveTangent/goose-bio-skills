---
name: biological-database-record-retrieval-and-identifier-resolution
description: "Resolve gene identifiers with a declared local mapping table or retrieve bounded public gene, transcript and protein records. Preserve ambiguous mappings and provenance; exclude remote bulk jobs, literature and clinical interpretation."
license: Apache-2.0
metadata:
  version: "0.12.0"
---

# Biological Database Record Retrieval and Identifier Resolution

`Preview + reviewed`; runtime and expert review were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Resolve up to 30,000 IDs using an explicit local mapping table, or retrieve bounded public gene, transcript, protein, or nucleotide records from UniProt, Ensembl, or NCBI. Preserve provider provenance and mapping ambiguity. Exclude syntax checks, literature, homology, structures, chemistry, remote bulk mapping, and clinical use.

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
asynchronous or remote bulk mapping are out of scope.

Pass `--max-bytes 16777216`. Count every HTTP response, including pagination,
toward the five-request limit; stop before a sixth.

## Local helper

Use [the bounded adapter and handoff guide](references/local-adapter.md) for
executable local work. This helper does not expand the network boundary.

Bounded offline mapping of up to 30,000 IDs is supported by the local helper;
the smaller public-network retrieval limits remain unchanged.

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

## Prepare local annotation resources

The same helper can convert explicitly selected TSV mapping exports or GMT gene sets to the bounded downstream formats. See [reference preparation](references/reference-preparation.md). It records resource declarations, input/output hashes and exact duplicate removal, retaining mapping ambiguity. DE handoffs now accept the bounded microarray limma result as well as DESeq2; the ranking metric is labeled explicitly.
