# Research Skill promotion gates

Every candidate remains on `research` until all applicable gates below pass.
Passing these gates supports promotion review; it does not establish universal
scientific validity or a better-than-baseline claim.

## Candidate record

- one recurring job, explicit inputs and output contract
- named owner, review cadence, risk tier, freshness date, and rollback boundary
- should-trigger, should-not-trigger, near-neighbor, and failure examples
- explicit scientific, privacy, network, tool, and human-review exclusions
- every unavailable approval, benchmark, runtime path, or telemetry item listed
  as `missing evidence`

## Evidence gates

- positive, boundary, invalid-input, fail-closed, and near-neighbor fixtures
- at least one blind routing holdout that was not used while authoring the Skill
- deterministic offline self-test for every bundled script
- exact file-backed fixture input and output hashes, with repeat runs identical
- create-new publication, no overwrite, bounded inputs, and partial/failed work
  never reported as completed
- tool, runtime, provider, version, and provenance closure appropriate to the job

For a networked candidate, also require an allowlisted read-only provider,
request/page/byte/rate limits, redirect and secret rejection, an offline response
fixture, failure cases such as rate limiting or truncation, and a successful
bounded public canary before promotion.

## Trust and review gates

- original implementation and source-clean/package validation pass
- dependency, data, provider, license, copyright, attribution, and NOTICE review
- scientific-contract, safety, trust, code, and named domain-method review
- no open P0 or P1 findings; accepted P2 items remain explicit
- existing routing, package, connector, and release checks do not regress

## Atomic promotion

- exact package digest and matching registry entry are reviewed together
- version, release state, assurance state, freshness, and rollback target agree
- candidate evidence is bound to the exact bytes being promoted
- promotion uses a reviewed pull request from `research` to `main`
- without stronger exact-package evaluation and expert/generalization evidence,
  keep `preview + reviewed` and state `formal_pass=false`

Any later byte change invalidates the prior candidate evidence and requires a
fresh check. A failed candidate is fixed forward on `research`; released history
is never rewritten.

## Wave R1 candidate-specific gates

These are tracked as candidate evidence, not current pass claims. At initial
implementation time, neither of the local candidates has a blind routing
holdout or named domain-method review, and the network candidate also lacks its
offline semantic response fixture and live canary.

### `missing-data-and-sensitivity-analysis`

- accept only a bounded local CSV/TSV table, one declared numeric outcome, and
  optional declared grouping columns
- report missingness and complete-case summaries without inferring MCAR, MAR,
  or MNAR from the observed pattern
- require caller-supplied outcome bounds or a caller-supplied delta grid before
  computing best/worst or tipping-style sensitivity results
- reproduce exact results on normal, all-observed, partially missing, and
  boundary fixtures; report all-missing overall or group strata as
  `not-estimable-no-observed-values`, and reject nonnumeric outcomes, invalid
  bounds, malformed tables, overwrite attempts, and unsupported requests for
  imputation or general model fitting
- receive a named statistical-method review before promotion

Current gaps: blind routing holdout, representative boundary fixtures bound to
exact hashes, and named statistical-method review.

### `protein-interface-contact-analysis`

- accept a bounded local PDB file, two explicit and distinct chain identifiers,
  and a positive finite heavy-atom distance cutoff
- return a deterministic residue-pair contact set with minimum atom distance and
  the exact parsing/cutoff policy; do not infer pockets, binding sites, buried
  surface area, affinity, function, docking, or molecular dynamics
- reproduce exact contacts on positive, no-contact, cutoff-boundary, alternate
  location, and repeated-run fixtures; reject malformed coordinates, missing or
  identical chains, unsupported formats, invalid cutoffs, and overwrite attempts
- receive a named structural-bioinformatics method review before promotion

Current gaps: blind routing holdout, representative deposited-structure
fixture evidence, and named structural-bioinformatics method review.

### `public-orthology-retrieval-and-qc`

- accept at most five exact Ensembl stable gene identifiers plus explicit,
  different canonical source and target species from the reviewed allowlist;
  require the source-species ID prefix and do not guess identifiers from symbols
- use only the reviewed Ensembl Compara read-only endpoint and preserve provider
  relationship type, cardinality, confidence fields, release context, request
  URL, response URL, bytes, and hashes without converting provider assertions
  into de novo orthology or functional-transfer claims
- pass an offline response fixture, reordered/empty/malformed response cases,
  wrong-species and non-gene identifier rejection, redirect/secret/rate-limit/
  truncation fail-closed cases, and one bounded anonymous live canary
- demonstrate at the package level that a batch of one to five IDs enforces the
  aggregate five-request, 16 MiB accepted-response, and three-request-per-second
  limits across the connector's individual single-ID calls
- retain the shared connector's exact homology path, canonical species/ID,
  query-policy, and output-safety gates; no Skill-local network bypass is permitted
- receive a named comparative-genomics method review before promotion

Current gaps: offline semantic response fixture, provider failure matrix,
bounded anonymous live canary, blind routing holdout, and named
comparative-genomics method review.
