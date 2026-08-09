---
name: ranked-gene-set-enrichment
description: "A user has a complete ranked gene list and requests cutoff-free gene-set enrichment. Exclude selected-list ORA, silent duplicate collapsing, causal claims, per-sample pathway scoring, or phenotype permutation without a separate matrix-and-label contract."
license: Apache-2.0
metadata:
  version: "0.3.0"
---

# Ranked Gene-set Enrichment

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Owns

Produce reproducible ranked-set enrichment statistics without converting the task into cutoff-based ORA. Exclusions are declared in the trigger above.

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

Prefer a versioned local collection. An explicit refresh authorizes bounded
public Enrichr library metadata reads; submitting a ranked list is a separate
remote job. Confirm sensitive rankings, remote jobs not already requested, or
unrequested bulk. On failure, use the pinned collection or return
`needs-tool`/partial. Record input and collection digests, provider, parameters,
hashes, and network or job status.

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
