---
name: protein-level-differential-abundance
description: "Analyze one declared contrast in already-normalized log2 protein abundances using a compatible local limma adapter. Exclude raw mass-spectrometry processing, normalization and RNA count models."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Protein-level Differential Abundance

`Preview + reviewed`; the fixed-runtime helper self-test passed. Agent runtime,
scientific benchmarking, representative-data evaluation, and expert review were
not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use for one offline limma differential-abundance contrast on a bounded, finite protein-by-sample matrix that the caller explicitly declares already normalized and log2 transformed, with exact sample metadata and an estimable categorical design. Exclude raw MS, PSM or peptide modeling, identification, protein inference, normalization, imputation, RNA counts, enrichment, biomarker selection, clinical use, and fallback tests.

## Owns

Fit one declared protein-level contrast with local R 4.4.1 and limma 3.60.6.
The Skill does not prepare, normalize, impute, identify, or select proteins.

## Inputs and intake

Require two bounded UTF-8 CSV/TSV files and a new JSON output path:

- a finite protein-by-sample matrix with one unique protein-ID column and unique sample columns;
- metadata with one row per exact matrix sample, unique sample IDs, one categorical condition, and only explicitly declared categorical covariates;
- caller confirmation that rows are protein-level and values are already normalized log2 abundances;
- one numerator-minus-denominator contrast, declared before fitting.

Inspect headers, exact sample joins, declarations, replication, and the local
adapter first. Ask one unresolved question with a recommendation, then wait:

1. **input-contract.** Are these finite values already normalized log2 protein-level abundances? Recommended: confirm from producer provenance; otherwise route to upstream QC or preparation.
2. **primary-contrast.** Which single numerator-minus-denominator condition contrast applies? Recommended: preregister one contrast before viewing results.
3. **design-covariates.** Which categorical metadata columns belong in the design? Recommended: include only prespecified adjustment terms and stop if the design is confounded.

An explicit local analysis request authorizes the bounded reads, fixed R
subprocess, private temporary work, and requested create-new report.

## Run

```text
python3 scripts/run_limma.py \
  --matrix ABUNDANCE.tsv --metadata SAMPLES.tsv --output NEW_REPORT.json \
  --protein-id-column protein_id --sample-id-column sample_id \
  --condition-column condition --numerator treated --denominator control \
  [--covariate-column batch] --declared-protein-level-normalized-log2
```

The Python 3.10+ executor accepts at most 16 MiB per input, 50,000 proteins,
256 samples, and four covariates. It invokes only `Rscript --vanilla` with the
bundled fixed script, requires exact R/limma versions, uses no shell or network,
and never substitutes a t-test or another model. Missing adapter, declaration,
sample, finite value, replication, full rank, residual degrees of freedom, or
estimable contrast fails closed without a report.

## Output contract

`completed` creates one deterministic JSON report containing input fingerprints,
the generated design formula and columns, design rank, residual degrees of
freedom, exact contrast, R/limma and script versions, and every protein in input
order with log2 effect, moderated standard error and t statistic, raw p-value,
BH-adjusted p-value, average abundance, total degrees of freedom, and B statistic.

Invalid input returns `invalid-input`; a missing or incompatible adapter returns
`needs-tool`; an unresolved declaration or contrast returns `needs-decision`.
Partial work is never `completed`, and an existing or unsafe output is never
replaced.

## Guardrails

- Treat the contrast effect as association in the declared design, not causality, biomarker evidence, or clinical authority.
- Reject missing/nonfinite values, duplicate proteins or samples, unmatched metadata, ambiguous scales, and rank-deficient or saturated designs.
- Exclude raw spectra, PSMs, peptides, identification/FDR, protein inference, normalization, imputation, RNA counts, enrichment, batch correction, feature selection, and clinical use.
- Never install tools, use the network, mutate inputs, follow input/output symlinks, escape the current directory, overwrite, or run caller-supplied code.
- Require researcher review of provenance, normalization, design, contrast, multiplicity, and biological interpretation.
