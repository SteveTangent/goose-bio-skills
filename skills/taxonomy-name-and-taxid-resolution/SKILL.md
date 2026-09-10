---
name: taxonomy-name-and-taxid-resolution
description: "Resolve declared organism names or TaxIDs through the NCBI taxonomy contract. Exclude gene identifiers, metagenomic classification and pathogen or clinical decisions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Taxonomy Name and TaxId Resolution

`Preview + reviewed`; runtime and expert evaluation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Resolve small sets of taxon names or NCBI TaxIds into current NCBI names, classified aliases, ranks, lineages, and merged or secondary IDs with provenance. Exclude gene mapping, descendants, taxdump, phylogeny, and clinical use.

## Owns

Resolve small public name or TaxId sets against NCBI Taxonomy without guessing
away ambiguous matches.

## Inputs

- up to 20 public TaxIds or literal names, including at most four names
- optional expected rank or lineage; output format and a new artifact path

## Intake

Inspect inputs and stated context first. An explicit public lookup authorizes
the bounded anonymous reads; ask for neither configuration nor a second
confirmation. Search first. If one result is required and context cannot resolve
multiple exact matches, ask one recommended question, then wait.

Decision order:

1. **ambiguous-name-match.** Which rank or lineage constrains the returned exact-name candidates? Recommended: use user-declared context; otherwise keep all candidates and return `needs-decision`.

## Execution

Use shared provider `ncbi-eutils`. For each name run quoted `[All Names]`
ESearch without History Server, then EFetch unique direct and candidate TaxIds
once. Cap one invocation at 20 candidates, five responses, 16 MiB, and three
requests per second. Missing adapter or network becomes `needs-tool`.

## Workflow

1. Preserve inputs; reject query operators, wildcards, control characters, and exceeded limits.
2. Keep every exact name candidate; filter only by declared rank or lineage and use Intake only when one result is required.
3. EFetch XML and extract current TaxId/name, classified names, rank, `LineageEx`, and `AkaTaxIds`.
4. Map every input to every result. Mark `merged-to` only when the requested TaxId differs from the current TaxId and appears in `AkaTaxIds`.

## Output contract

Return `completed`, `partial`, `needs-decision`, `needs-tool`, or
`invalid-input`. A completed result includes:

- per-input match status and name class; current TaxId/name, rank, lineage,
  classified names, secondary TaxIds, and one-to-many or merged mappings
- not-returned inputs, assumptions, omissions, provider, request parameters,
  access time, request count, response fingerprint, and available update metadata

Truncated, failed, skipped, or unresolved multi-match work is not `completed`.
A non-returned TaxId is not proven deleted. Never overwrite a path.

## Boundaries

See [runtime boundaries](references/runtime-boundaries.md). NCBI's current name
is a provider assertion; its lineage is classification, not phylogeny.

- Send only declared public names, TaxIds, and bounded parameters; preserve spelling, matches, classes, and mappings.
- Exclude paid providers, credentials, arbitrary URLs, uploads, writes, fuzzy search, gene mapping, descendants, taxdump, phylogeny, and clinical use.
- Do not send sensitive, private, patient, unpublished, or controlled data.
- Require researcher review; this Skill has no clinical authority.
