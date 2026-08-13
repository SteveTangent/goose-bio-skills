---
name: public-orthology-retrieval-and-qc
description: "Retrieve Ensembl Compara orthology assertions for up to five exact public Ensembl gene stable IDs between explicit supported canonical species names: homo_sapiens, mus_musculus, rattus_norvegicus, or danio_rerio. Preserve relationship type, cardinality, confidence fields, release, and provenance. Exclude symbols, identifier resolution, similarity search, de novo inference, functional transfer, tree inference, and clinical use."
license: Apache-2.0
metadata:
  version: "0.9.0"
---

# Public Orthology Retrieval and QC

`Preview + reviewed`; live runtime, scientific benchmark, and expert review were not performed.

## Owns

Retrieve a small, explicit set of public Ensembl Compara orthology assertions
without converting similarity or provider confidence into biological proof.

## Inputs

- one to five exact public Ensembl gene stable IDs from one source species
- explicit, different canonical source and target names chosen from
  `homo_sapiens`, `mus_musculus`, `rattus_norvegicus`, and `danio_rerio`
- optional output format and a new artifact path

## Intake

Inspect the identifiers and species first. An explicit public retrieval request
authorizes the bounded anonymous reads below; ask for neither configuration nor
a second confirmation. Inputs outside this narrow contract are `invalid-input`;
do not guess symbols, species, or another Compara division.

## Execution

Use shared provider `ensembl-rest`. For each ID, request JSON from
`/homology/id/{source_species}/{id}` with the exact reviewed parameters:
`target_species`, `type=orthologues`, `sequence=none`, `aligned=0`,
`format=condensed`, and `content-type=application/json`. The connector enforces
stable gene IDs, distinct species, and fixed parameters. This Skill requires one
anonymous, non-paginated GET per stable ID and a new output path. Missing adapter
or network becomes `needs-tool`.

## Workflow

1. Preserve every input exactly; reject symbols, mixed source species, query
  syntax, aliases, source-species/ID prefix mismatches, control characters, or
  exceeded limits.
2. Make one homology GET per ID and account for every requested ID.
3. Preserve every returned source-target assertion and provider field; never
   select a single target from one-to-many or many-to-many results.
4. Report provider relationship type separately from returned target count.
   Missing confidence fields remain missing, not false or zero.

## Output contract

Return `completed`, `partial`, `needs-tool`, or `invalid-input`. A checked
successful empty result may be `completed`, but mark its input
`no-ortholog-returned`. Include:

- requested and returned IDs/species, provider relationship type, relationship
  cardinality, taxonomy level, method, and returned target count
- every exposed confidence or QC field and its missingness, without recomputing
  or upgrading it
- Ensembl release metadata when exposed, access time, exact redacted requests,
  request count, response fingerprints, omissions, and errors

Failed, truncated, skipped, or unaccounted work is not `completed`. Never
overwrite an artifact path.

## Boundaries

See [runtime boundaries](references/runtime-boundaries.md). Orthology type and
confidence are Ensembl assertions, not proof of conserved function.

- Send only declared public stable IDs, species, and fixed parameters.
- Exclude symbols, identifier resolution, similarity search, de novo orthology,
  paralogue analysis, functional transfer, tree inference, bulk retrieval, and
  clinical use.
- Do not send patient, private, unpublished, controlled, or credential-bearing data.
- Require researcher review; this Skill has no clinical or diagnostic authority.
