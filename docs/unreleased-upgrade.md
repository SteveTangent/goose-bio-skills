# Current preview changes

The current preview has **56 packages and 37 bounded helpers**, across 13 Domains and 27 Clusters. Twelve packages use 0.11.0 and 44 retain their previous 0.10.0 bytes. The immutable collection VERSION stays 0.9.0; main is a reviewed preview, not a newly tagged or stable release.

| Area | Delivered behavior |
| --- | --- |
| Six new jobs | Continuous two-group effects, declared correlations, result concordance, one-platform GEO matrix preparation, marker evidence review and one-cell-type pseudobulk aggregation |
| Six enhanced jobs | Sample-table validation, FastQC summaries, small h5ad QC and core exploration, figures and report/methods assembly |
| Interaction | Every package uses available facts, focused clarification, relevant terminology and evidence-backed corrections |
| Installation | Six task bundles, complete-package digest checks, create-new installation and explicit dependency inventory coverage |
| Maintenance | Unified current catalog; installer regression included in quick/CI checks; previous release and experiment evidence retained |

## Evidence and limits

The expansion passed 61 small-input checks, including one bounded real GEO matrix; existing efficiency paths passed 142 checks. A small single-cell object was exercised through QC, exploration and pseudobulk, with the latter fitted by the existing DESeq2 adapter. Linux/macOS CI passed after fixed R dependencies and connector file-publication identity handling were corrected.

These checks establish bounded execution and reviewed package contracts. They do not establish representative biological performance, clinical validity, human-expert review or measured Agent superiority. All packages remain `preview + reviewed`.

The current maintenance gate is `python3 scripts/verify.py quick`; `release` adds retained connector and R1–R5 deterministic replay checks. The installer self-test is now included in both modes. A dependency inventory with unchecked helpers does not report readiness; consult each adapter before execution.

Start with [task bundles](task-bundles.md), the [small expansion example](../examples/expansion/README.md), [user dialogue examples](user-experience.md), or the [full catalog](catalog.md). The [earlier stage notes](upgrade-history-2026-09-10.md) retain historical counts, pending states and evidence boundaries.

## Optional workflow handoffs

A repository companion now preserves declared facts and checks native results across small statistics, public-expression and single-cell flows. It records dependencies and source outcomes, invalidates changed results, accepts explicit failure notes and creates a linked overview. The 56 package digests remain unchanged; no new scientific adapter is introduced. See [workflow usage](analysis-workflow.md). The normal quick/CI entrypoint includes its bounded handoff regressions.
