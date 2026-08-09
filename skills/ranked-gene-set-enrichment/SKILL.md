---
name: ranked-gene-set-enrichment
description: "A user has a complete ranked gene list and requests gene-set enrichment without selecting a significance cutoff. Exclude: selected-list ORA; silent duplicate collapsing; causal pathway claims; per-sample pathway activity scoring; phenotype permutation without a separate expression-matrix and label contract."
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

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **ranked-duplicate-policy.** How should duplicate identifiers be collapsed? Recommended: Use one deterministic rule declared before enrichment.
2. **ranked-tie-policy.** How should tied ranking statistics be ordered? Recommended: Use a deterministic tie policy and report tie prevalence.
3. **ranked-permutation-policy.** Which gene-set permutation count and random seed should the preranked run use? Recommended: Use gene-set permutations with a recorded seed; phenotype permutation requires a separate expression-matrix and sample-label contract.

## Workflow

1. Validate ranking completeness, direction, ties and duplicate identifiers.
2. Freeze gene-set release and deterministic duplicate policy.
3. Run preranked enrichment with gene-set permutations and a recorded seed.
4. Report leading edges, stability, multiplicity and interpretation limits.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- enrichment scores, normalized scores and multiplicity results
- leading-edge features
- ranking, duplicates, seed, permutations and release provenance

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Record the ranking statistic, direction, duplicate-gene policy, tie handling, and complete ranked input
- For preranked input use gene-set permutation only, with permutation count and random seed
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
