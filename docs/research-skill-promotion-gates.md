# Research Skill promotion gates

Wave R1 passed the same-level `preview + reviewed` minimum gates and entered
the v0.7.0 Beta. Its retained evidence remains below as the release baseline;
future candidates reuse the generic gates and add their own scoped section.

The Wave R3 shortlist and its candidate-specific gates are recorded in
[research-wave-r3-candidates.md](research-wave-r3-candidates.md). Wave R2's
completed research package and evidence remain recorded in
[research-wave-r2-candidates.md](research-wave-r2-candidates.md).

Wave R2 has now passed its research-branch minimum implementation gate. The
[Wave R2 minimum-reliability record](../evals/research-wave-r2-minimal-reliability-v0.1.json)
binds the retained small fixtures, repeat outputs, package digests, route
observations, and independent reviews. This permits continued research use and
review, not direct merge into the existing v0.7.0 release; any later promotion
requires a new atomic collection version and a final-byte rerun.

Wave R3 has also passed its research-branch minimum implementation gate. The
[Wave R3 minimum-reliability record](../evals/research-wave-r3-minimal-reliability-v0.1.json)
binds its three exact packages, 60/60 retained checks run twice, 62 canonical
routes, six independent holdout routes, and independent P0/P1/P2=0 reviews.
Real minimap2 execution remains explicitly unverified. As with Wave R2, this
permits supervised research use but not direct promotion into v0.7.0.

Every candidate remains on `research` until the applicable minimum gates for
the target release level pass. For the current target, that level is the same
`preview + reviewed` Beta assurance used on `main`; it is not `evaluated`,
`stable`, a universal scientific-validity claim, or a better-than-baseline
claim.

The [Wave R1 bounded smoke record](../evals/research-wave-r1-bounded-smoke-v0.1.json)
records the initial small-data diagnostic. The
[Wave R1 minimum-reliability record](../evals/research-wave-r1-minimal-reliability-v0.1.json)
adds a retained offline replay (84/84 checks across the three candidates), the
first execution of a six-case independent routing set (6/6 expected routes,
zero forbidden selections, and zero unnecessary questions), and the prior
single bounded orthology live canary. This is intentionally narrow evidence.

## Candidate record

- one recurring job, explicit inputs and output contract
- named owner, review cadence, risk tier, freshness date, and rollback boundary
- should-trigger, should-not-trigger, near-neighbor, and failure examples
- explicit scientific, privacy, network, tool, and human-review exclusions
- every unavailable approval, benchmark, runtime path, or telemetry item listed
  as `missing evidence`

## Minimum evidence gates for `preview + reviewed`

- positive, boundary, invalid-input, fail-closed, and near-neighbor coverage
  proportionate to the narrow Beta contract
- at least one independently executed positive/neighbor routing pair per
  candidate, preserved after first execution as a visible regression fixture
- deterministic offline self-test for every bundled script
- retained small fixture inputs and expected outputs bound to exact hashes, with
  repeat runs identical
- create-new publication, no overwrite, bounded inputs, and invalid/failed work
  never reported as completed
- tool, runtime, provider, version, and provenance boundaries recorded honestly

For a networked candidate, same-level Beta promotion also requires an
allowlisted read-only provider, reviewed request/page/byte/rate bounds, redirect
and secret rejection in the shared connector, a retained offline valid/empty/
malformed response replay, and one successful bounded anonymous public canary.

## Trust and review gates

- original implementation and source-clean/package validation pass
- dependency, data, provider, license, copyright, attribution, and NOTICE review
- scientific-contract, safety, trust, and code review appropriate to the narrow
  Beta claim
- no open P0 or P1 findings; accepted P2 items remain explicit
- existing routing, package, connector, and release checks do not regress

## Stronger future evidence

The following are valuable for later `evaluated` or `stable` promotion, but are
not blockers for a same-level `preview + reviewed` Beta merge:

- named external domain-method or human-expert review
- large or representative datasets and cross-study generalization
- a complete provider, platform, parser, and failure-mode matrix
- formal exact-package agent-runtime evaluation and baseline comparison
- claims of scientific performance, availability, or superiority

Until those exist, manifests must keep runtime evaluation, scientific benchmark,
and human-expert review as `not-performed`, retain explicit unverified
boundaries, and keep `formal_pass=false` in evaluation evidence.

## Atomic promotion

- exact package digest and matching registry entry are reviewed together
- version, release state, assurance state, freshness, and rollback target agree
- candidate evidence is bound to the exact bytes being promoted
- promotion uses a reviewed change from `research` to `main`
- without stronger exact-package evaluation and expert/generalization evidence,
  keep `preview + reviewed` and state `formal_pass=false`

Any later byte change invalidates the prior candidate evidence and requires a
fresh check. A failed candidate is fixed forward on `research`; released history
is never rewritten.

## Wave R1 candidate-specific gates

The status below is limited to the minimum same-level Beta checks. Each
candidate still needs final exact-byte digest/registry binding and the final
no-P0/P1 review before promotion.

### `missing-data-and-sensitivity-analysis`

- accept only a bounded local CSV/TSV table, one declared numeric outcome, and
  optional declared grouping columns
- report missingness and complete-case summaries without inferring MCAR, MAR,
  or MNAR from the observed pattern
- require caller-supplied outcome bounds and a caller-supplied delta grid before
  computing bounded sensitivity scenarios
- allow a present outcome column whose overall values or individual group values
  are all missing, and report those summaries as
  `not-estimable-no-observed-values`; reject a missing declared column, a table
  with no data rows, malformed input, nonnumeric observed outcomes, invalid
  bounds, overwrite attempts, and requests for imputation or general model
  fitting

Minimum evidence recorded: the retained small replay covers partial missingness,
an all-missing outcome column, nonnumeric input, deterministic output, and
no-overwrite behavior; the independent positive/near-neighbor routing pair
selected the expected Skills with no question. Named statistical-method review,
representative study tables, broader boundary fixtures, and inferential models
remain future `evaluated`/`stable` enhancements.

### `protein-interface-contact-analysis`

- accept a bounded local legacy PDB file, two explicit and distinct chain
  identifiers, and a positive finite heavy-atom distance cutoff
- return a deterministic residue-pair contact set with minimum atom distance and
  the exact parsing/cutoff policy; do not infer pockets, binding sites, buried
  surface area, affinity, function, docking, or molecular dynamics
- reject malformed coordinates, missing or identical chains, unsupported
  formats, invalid cutoffs, and overwrite attempts; route requests requiring
  mmCIF or retained alternate conformers away from this helper

Minimum evidence recorded: the retained small replay covers one exact-cutoff
contact, a no-contact result, malformed input, deterministic output, and
no-overwrite behavior; the independent positive/unsupported-mmCIF routing pair
selected or declined the Skill as expected with no question. Named
structural-bioinformatics review, representative deposited structures, large
interfaces, alternate conformers, and multiple-model coverage remain future
`evaluated`/`stable` enhancements.

### `public-orthology-retrieval-and-qc`

- accept at most five exact Ensembl stable gene identifiers plus explicit,
  different canonical source and target species from the reviewed allowlist;
  require the source-species ID prefix and do not guess identifiers from symbols
- use only the reviewed Ensembl Compara read-only endpoint and preserve provider
  relationship type, cardinality, confidence fields, release context, request
  URL, response URL, bytes, and hashes without converting provider assertions
  into de novo orthology or functional-transfer claims
- retain the shared connector's exact homology path, canonical species/ID,
  query-policy, output-safety gates, five-request limit, 16 MiB accepted-response
  limit, and three-request-per-second policy; no Skill-local network bypass is
  permitted

Minimum evidence recorded: the retained offline replay covers one exact request,
one one-to-one response, one empty result, one malformed response, deterministic
payload/provenance output, and no-overwrite behavior; the independent exact-ID/
local-sequence-neighbor pair selected the expected Skills with no question; one
bounded anonymous homo_sapiens-to-mus_musculus live canary passed. Named
comparative-genomics review, end-to-end agent normalization, multi-ID aggregate-
limit execution, reordered and multi-target payloads, the full provider failure
matrix, and broad availability remain future `evaluated`/`stable` enhancements.
