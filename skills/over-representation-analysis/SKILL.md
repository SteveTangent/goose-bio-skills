---
name: over-representation-analysis
description: "Test gene-set over-representation from selected genes and an explicit measured background universe. Exclude ranked enrichment, identifier guessing and mechanistic or clinical conclusions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Over-representation Analysis

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user has a selected gene list plus an appropriate measured or tested universe and requests categorical enrichment. Exclude: ranked-list enrichment; using the whole genome as an unexamined default universe; causal pathway claims.

## Owns

Produce an auditable contingency-test enrichment result for a selected set against a defensible universe. Apply the detailed scope below.

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

Prefer versioned local data. Explicit refresh permits bounded QuickGO or
Enrichr metadata reads; KEGG also needs its terms acknowledgement. No reviewed
list-submission adapter exists, so return `needs-tool` without asking to upload
or implying a job. Never send patient, PHI, controlled data, credentials, or
secrets. Record releases, digests, provider, hashes, and network status.

## Local helper

Use [the bounded adapter and handoff guide](references/local-adapter.md) for
executable local work. This helper does not expand the network boundary.

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
