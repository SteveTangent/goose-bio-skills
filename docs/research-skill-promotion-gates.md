# Research Skill promotion gates

Wave R1 passed the same-level `preview + reviewed` minimum gates and entered
the v0.7.0 Beta. Its retained evidence remains below as the release baseline;
future candidates reuse the generic gates and add their own scoped section.

The Wave R3 shortlist and its candidate-specific gates are recorded in
[research-wave-r3-candidates.md](research-wave-r3-candidates.md). Wave R2's
completed research package and evidence remain recorded in
[research-wave-r2-candidates.md](research-wave-r2-candidates.md).
Wave R4's six one-job candidates and their exact small-data gates are recorded
in [research-wave-r4-candidates.md](research-wave-r4-candidates.md).
The implemented, research-only Wave R5 shortlist is recorded in
[research-wave-r5-candidates.md](research-wave-r5-candidates.md).

Wave R2 passed its research-branch minimum implementation gate and entered the
v0.8.0 Beta as `preview + reviewed`. The
[Wave R2 minimum-reliability record](../evals/research-wave-r2-minimal-reliability-v0.1.json)
binds the retained small fixtures, repeat outputs, package digests, route
observations, and independent reviews; the v0.8.0 release record binds its
final package and registry bytes.

Wave R3 also passed its research-branch minimum implementation gate and entered
the v0.8.0 Beta as `preview + reviewed`. The
[Wave R3 minimum-reliability record](../evals/research-wave-r3-minimal-reliability-v0.1.json)
binds its three exact packages, 60/60 retained checks run twice, the then-current 62 canonical
routes, six independent holdout routes, and its then-current package reviews.
A later bounded synthetic macOS ARM64 canary ran the exact alignment executor
twice with real minimap2 2.31-r1302 and passed deterministic output and
no-overwrite checks. That narrow integration evidence is not formal agent
runtime evaluation, representative scientific validation, or a reason to
change assurance. The v0.8.0 release record binds the final package and
registry bytes; the canary remains point-in-time evidence.

Wave R4 passed its research-branch minimum gate and entered the v0.8.0 Beta as
`preview + reviewed`. Its retained runner passed
twice with 192/192 checks across six final packages, and a 12-prompt independent
contract-routing diagnostic produced six intended selections and six correct
no-Skill boundaries with no forbidden selection or unnecessary question. This
remains small-data `preview + reviewed` evidence, not formal scientific or
model-runtime evaluation. The v0.8.0 release record binds its final package and
registry bytes.
Its exact-ID network boundary also has one retained bounded anonymous
[ClinVar canary](../evals/research-wave-r4-clinvar-canary-v0.1.json); that
point-in-time provider check does not establish availability or clinical validity.
The final cross-wave publisher seal review closed all P0/P1 findings and retained
one accepted, non-blocking P2 for the explicitly documented low-level local-directory
concurrency and exceptional temporary-file cleanup boundary.

Wave R5 is implemented on `research` only and has not been promoted to `main`.
Its retained small-data runner covers four package self-tests, exact
package/input/output hashes, two valid runs with byte-identical outputs and
event lines, bounded semantic oracles, invalid/no-output boundaries, and
create-new/no-overwrite behavior. The independent first routing pass chose the
intended Skill or no-Skill boundary in 8/8 cases with zero forbidden selection
and action-compatible handling in 8/8. It asked two conservative questions
where the fixed oracle expected none, so exact question-count agreement is
6/8. This is retained as a research diagnostic rather than rewritten into a
pass. Wave R5 remains `preview + reviewed`; formal evaluation and `main`
promotion are false.

## Wave R5 research-only gates

- `bulk-rnaseq-gene-count-matrix-assembly`: accept at least two completed
  schema-1.0 single-sample count reports only when GTF digest, every gene tuple,
  and the full assignment contract agree; sort genes/samples; never count,
  complete genes, normalize, batch-correct, or model.
- `amplicon-beta-diversity-distance-analysis`: compute only pairwise
  Bray-Curtis and binary Jaccard from unchanged nonnegative integer feature
  rows; keep any zero-depth pair not estimable; never rarefy, ordinate, test
  groups, identify pathogens, or interpret biology.
- `two-group-log-rank-survival-comparison`: compare exactly two prespecified
  right-censored groups with one unadjusted two-sided Mantel-Cox test, event
  ties before censor removal, and structured zero-variance output; never emit
  significance, Cox, competing-risk, prediction, or treatment decisions.
- `flow-cytometry-arcsinh-transformation`: apply only caller-supplied positive
  channel cofactors to an extracted event table, preserving unselected tokens;
  never parse FCS, compensate, choose cofactors, gate, label, or interpret.

All four candidates are local/network-free, first-release packages with
remove-package rollback, and remain outside the 44-package v0.8.0 `main` Beta.

Every future candidate remains on `research` until the applicable minimum gates for
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

Create-new publication is tested against ordinary pre-existing targets,
partial writes, cleanup failures, and observed file-identity replacement. It
does not claim lock-free security against a malicious process that already has
write access to the same directory and can replace a name between one identity
check and the immediately following unlink system call; callers needing that
threat model must provide directory isolation or external locking. An
exceptional failure before a newly created temporary file's identity can be
captured may also leave that randomly named, mode-0600 temporary file for
manual cleanup; it must never be treated as a completed result.

For a networked candidate, same-level Beta promotion normally also requires an
allowlisted read-only provider, reviewed request/page/byte/rate bounds, redirect
and secret rejection in the shared connector, a retained offline valid/empty/
malformed response replay, and one successful bounded anonymous public canary.
The v0.8.0 release records an explicit waiver instead of rerunning the ClinVar
canary: its prior canary is point-in-time only, while the exact release parser,
connector, and package bytes are covered by retained offline checks. This does
not establish current provider availability.

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

The status below records the minimum same-level Beta checks used before Wave R1
entered v0.7.0. Its final exact-byte digest/registry binding and no-P0/P1 review
were completed by that atomic release.

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
