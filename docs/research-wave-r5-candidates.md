# Research Wave R5 candidate shortlist

Status: promoted together into the v0.9.0 `main` Beta as four
`preview + reviewed` packages. The packages retain the same small-data,
local-only reliability boundary; promotion does not make them evaluated or
stable.

## Implemented first four

1. `bulk-rnaseq-gene-count-matrix-assembly` — assemble two or more validated
   single-sample count reports into one exact gene-by-sample integer matrix.
   Require matching annotation and gene-row contracts; exclude counting,
   normalization, batch correction, and differential expression.
2. `amplicon-beta-diversity-distance-analysis` — compute Bray–Curtis and
   presence/absence Jaccard distances from one exact nonnegative feature table.
   Preserve zero-depth pairs as not estimable; exclude rarefaction, ordination,
   PERMANOVA, differential abundance, and biological interpretation.
3. `two-group-log-rank-survival-comparison` — run one fixed two-sided
   Mantel–Cox comparison for two declared right-censored groups. Exclude KM
   curve estimation, Cox models, covariates, competing risks, and clinical
   prediction.
4. `flow-cytometry-arcsinh-transformation` — apply caller-supplied positive
   per-channel cofactors to selected columns in an extracted event table.
   Exclude cofactor selection, FCS parsing, compensation, gating, labels, and
   interpretation.

## Deferred fifth candidate

`flow-cytometry-rectangular-gate-application` is valuable but should wait until
the transformation candidate proves the flow-table handoff. It would apply one
explicit two-channel rectangle with declared inclusive/exclusive boundaries;
it must not discover gates, build hierarchies, transform data, or label cells.

## Minimum admission gate (passed)

Each implemented candidate needs one exact small positive fixture, one invalid
or fail-closed fixture, deterministic repeated output, create-new/no-overwrite
checks, one positive plus one near-neighbor routing prompt, package digest
binding, and independent review with no open P0 or P1. These checks support the
narrow Beta boundary only; formal runtime evaluation, representative
benchmarking, expert review, clinical use, and superiority claims remain
outside scope.

The four package self-tests pass with 39, 46, 48, and 32 checks respectively.
The retained Wave R5 runner binds exact packages, inputs, outputs, semantic
oracles, invalid/no-output boundaries, two-run determinism, and no-overwrite.
Its first independent routing pass selected the intended Skill or no-Skill
boundary in all eight cases with no forbidden selection, but two positive
cases prompted conservatively where the fixed oracle expected no question;
therefore exact question-count agreement is 6/8. This is a non-blocking
research diagnostic, not agent-runtime or generalization evidence.
