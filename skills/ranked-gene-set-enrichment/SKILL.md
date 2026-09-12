---
name: ranked-gene-set-enrichment
description: "Analyze enrichment from a complete declared gene ranking and compatible gene sets. Exclude selected-gene over-representation, identifier guessing and mechanistic conclusions."
license: Apache-2.0
metadata:
  version: "0.12.0"
---

# Ranked Gene-set Enrichment

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


Detailed scope: A user has a complete ranked gene list and requests cutoff-free gene-set enrichment. Exclude selected-list ORA, silent duplicate collapsing, causal claims, per-sample pathway scoring, or phenotype permutation without a separate matrix-and-label contract.

## Owns

Produce reproducible ranked-set enrichment statistics without converting the task into cutoff-based ORA. Apply the detailed scope below.

## Inputs

- complete preranked gene list
- ranking metric and direction
- organism and identifier namespace
- versioned gene sets, gene-set permutation count, and seed

## Intake

Inspect safe facts first. Ask one recommended question only when a
result-changing choice remains, then wait; otherwise continue authorized work.

Decision order:

1. **ranked-duplicate-policy.** How should duplicates collapse? Recommended: declare one deterministic rule.
2. **ranked-tie-policy.** How should ties order? Recommended: use a deterministic policy and report prevalence.
3. **ranked-permutation-policy.** Which count and seed? Recommended: use gene-set permutations; phenotype permutation needs a separate matrix-and-label contract.

## Public network execution

Prefer versioned local data. Explicit refresh permits bounded Enrichr metadata
reads. No reviewed ranked-list submission adapter exists, so return
`needs-tool` without asking to upload or implying a job. Never send patient,
PHI, controlled data, credentials, or secrets. On failure use pinned data or a
non-completed status. Record input/collection digests, provider, parameters,
hashes, and network status.

## Local helper

Use [the bounded adapter and handoff guide](references/local-adapter.md) for
executable local work. This helper does not expand the network boundary.

## Workflow

1. Validate ranking completeness, direction, ties and duplicate identifiers.
2. Freeze the local or retrieved gene-set release and deterministic duplicate policy.
3. Run preranked enrichment with gene-set permutations and a recorded seed.
4. Report leading edges, stability, multiplicity and interpretation limits.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- enrichment scores, normalized scores and multiplicity results
- leading-edge features
- ranking, duplicates, seed, permutations and release provenance

Record versions and limitations; never fabricate execution.

## Runtime and scientific boundaries

See [runtime boundaries](references/runtime-boundaries.md). Rolling libraries do
not replace a versioned collection or make results causal.

## Guardrails

- Record the ranking statistic, direction, duplicate-gene policy, tie handling, and complete ranked input
- For preranked input use gene-set permutation only, with permutation count and random seed
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority

The current mapping handoff names its signed statistic and positive direction. Match both declarations exactly; a microarray moderated t statistic must not be relabeled as a DESeq2 Wald statistic.
