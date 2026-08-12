# Research Wave R4 candidates

Status: minimum-reliability gate passed on `research`. These six packages are not
part of the v0.7.0 Beta; promotion still requires a later atomic release and a
fresh final-byte rerun.

Wave R4 favors common user jobs with a compact, inspectable oracle. It does not
attempt six more broad end-to-end pipelines.

## 1. Bulk RNA-seq gene counting from alignment

Slug: `bulk-rnaseq-gene-counting-from-alignment` (D04 / C12)

Owns one bounded primary single-end SAM plus an exact exon GTF, an explicit
strandedness mode and MAPQ floor, and publishes gene counts plus assignment
categories. It excludes read alignment, paired fragments, transcript
quantification, normalization and differential expression.

Minimum gate: a two-gene synthetic GTF and eight-record SAM must exercise
unique, spliced, ambiguous, no-feature, low-MAPQ and unmapped categories with
exact reconciliation; malformed or multi-sample SAM, untrusted row semantics,
resource overflow and overwrite must fail closed.

## 2. Junction PSI and delta analysis

Slug: `junction-psi-and-delta-analysis` (D04 / C13)

Owns per-sample PSI and one declared two-group delta from already prepared
inclusion/exclusion integer counts under an explicit minimum-coverage rule. It
excludes BAM parsing, junction discovery, isoform reconstruction, statistical
significance and gene differential expression.

Minimum gate: a three-event by six-sample fixture must produce exact PSI,
not-estimable low-coverage states and exact deltas; invalid counts, group joins,
duplicate IDs, missing declarations and overwrite must fail closed.

## 3. Amplicon alpha-diversity analysis

Slug: `amplicon-alpha-diversity-analysis` (D07 / C20)

Owns observed-feature count, natural-log Shannon and Simpson diversity for each
sample in an exact nonnegative feature-by-sample table. Zero-depth samples are
reported as not estimable. It excludes rarefaction, normalization, beta
diversity, differential abundance, contamination and taxonomy claims.

Minimum gate: a four-feature by three-sample fixture including one zero-depth
sample must match hand-calculated metrics; negative/fractional/oversized counts,
duplicate identifiers, ambiguous orientation and overwrite must fail closed.

## 4. Flow-cytometry compensation application

Slug: `flow-cytometry-compensation-application` (D08 / C24)

Owns applying one explicitly supplied, source-row by observed-column spillover
matrix to matching numeric channels in an already extracted event table. It
excludes FCS parsing, matrix estimation, transformations, gating and cell labels.

Minimum gate: a three-channel by five-event fixture must reconstruct exact
compensated values with deterministic outputs; mismatched channels, malformed
numbers, implausible or ill-conditioned matrices, partial publication and
overwrite must fail closed.

## 5. Kaplan–Meier survival analysis

Slug: `kaplan-meier-survival-analysis` (D12 / C36)

Owns deterministic Kaplan–Meier steps, at-risk/event/censor counts and median
survival for one time/event table, optionally with one declared stratum. It
excludes Cox models, competing risks, interval censoring, causal claims and
clinical prediction.

Minimum gate: a six-subject fixture with ties, censoring and two strata must
match an exact curve and median oracle; invalid times/events, duplicate subjects,
empty risk sets, unsupported strata and overwrite must fail closed.

## 6. Human variant evidence retrieval

Slug: `human-variant-evidence-retrieval` (D13 / C38)

Owns bounded retrieval or exact replay normalization for at most five exact
ClinVar Variation IDs or VCV accessions, preserving provider classifications,
review status, conditions, dates and provenance. It excludes free-text variant
resolution, ACMG classification, diagnosis, treatment, scoring and conflict
resolution.

Minimum gate: retained official-shape fixtures for one ordinary assertion, one
conflicting aggregate and one empty result must normalize exactly; malformed
responses, identifier mismatch, truncation, secret-bearing requests and
overwrite must fail closed. Live public retrieval is optional only when the
shared reviewed connector supports the exact endpoint; otherwise the package
must return `needs-tool` rather than improvise.

## Shared gate

Before these candidates can be considered for a later atomic Beta release:

1. all six package self-tests and two retained small-data replays pass on final
   package digests;
2. each package has a positive route plus a near-neighbor or unsupported route,
   with no forbidden selection in the independent first execution;
3. valid output, malformed input, deterministic bytes, create-new publication,
   no-overwrite and package binding are checked;
4. local tools and public providers remain explicit, bounded and fail closed;
5. full repository regression and independent review report P0=0 and P1=0;
6. assurance remains `preview + reviewed`; formal runtime, representative
   scientific benchmarking, expert review, scale, clinical use and superiority
   claims remain outside this minimum.

## Minimum evidence recorded

The retained offline runner passed twice with 192/192 checks and identical JSON
events. It binds all six final package digests, small input/output hashes,
self-tests, valid semantics, one invalid boundary, deterministic bytes, and
create-new/no-overwrite behavior. ClinVar replay uses a synthetic sidecar bound
to the fixture and performs no network call. A separate
[bounded public ClinVar canary](../evals/research-wave-r4-clinvar-canary-v0.1.json)
retains its point-in-time package, connector, payload, provenance, semantic-oracle,
and publication hashes; current publication-hardening bytes are covered by the
offline replay. It is narrow provider-shape evidence only.

An independent first-pass routing diagnostic judged 12 held-out prompts before
opening their oracle file: all six positive prompts selected the intended Skill,
all six near-neighbor requests selected no Skill, no forbidden neighbor was
selected, and no unnecessary question was asked. This is contract-routing
evidence for hand-authored prompts, not model-generalization evidence.

Independent final seal review closed all P0 and P1 findings within this minimum
scope and retained one accepted, non-blocking P2 for the documented low-level
local-directory concurrency and exceptional temporary-file cleanup boundary.
The exact bindings and remaining evidence are recorded in
[`research-wave-r4-minimal-reliability-v0.1.json`](../evals/research-wave-r4-minimal-reliability-v0.1.json).
