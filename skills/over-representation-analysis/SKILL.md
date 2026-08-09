---
name: over-representation-analysis
description: "A user has a selected gene list plus an appropriate measured or tested universe and requests categorical enrichment. Exclude: ranked-list enrichment; using the whole genome as an unexamined default universe; causal pathway claims."
license: Apache-2.0
metadata:
  version: "0.3.0"
---

# Over-representation Analysis

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce an auditable contingency-test enrichment result for a selected set against a defensible universe. Exclusions are declared in the trigger above.

## Inputs

- selected gene identifiers
- tested universe
- organism and identifier namespace
- versioned gene-set collection

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **ora-universe.** Which features were actually eligible to enter the selected set? Recommended: Use measured or statistically tested features as the universe, not the whole genome by default.

## Public network execution

Prefer a versioned local collection. An explicit refresh authorizes bounded
public reads from `quickgo` or Enrichr library metadata; `kegg-rest` also
requires its academic-terms acknowledgement. Enrichr gene-list submission is a
separate upload. Confirm sensitive lists, remote jobs, or unrequested bulk.
Record collection release, input digests, provider, hashes, and network status.

## Workflow

1. Validate namespace, organism and selected-list membership in the universe.
2. Freeze the local or retrieved gene-set release and mapping policy.
3. Compute contingency statistics and multiplicity correction.
4. Report overlaps, unmapped genes, universe sensitivity and non-causal interpretation.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- enrichment table with overlap and adjusted significance
- identifier mapping and unmapped records
- universe, database release and test provenance

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Retrieval does not
establish mapping, universe choice, causality, or reproducibility.

## Guardrails

- Declare organism, identifier namespace and mapping, selected set, tested universe, and exact gene-set release or digest
- Use a one-sided over-representation test under an explicit contingency-table contract
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
