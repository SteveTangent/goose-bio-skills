# Current preview changes — 2026-09-12

Current main preview: **57 packages, 38 bounded helpers, 13 Domains and 27 Clusters**. Six packages use 0.12.0, nine retain 0.11.0 and 42 retain 0.10.0. All remain preview + reviewed. The immutable v0.9.0 collection and VERSION are preserved; this merge does not create a new tag or stable release.

| Area | Delivered behavior |
| --- | --- |
| New analysis | Normalized log2 microarray limma: one platform, independent two-group contrast, at most one categorical adjustment, effect/CI/BH and QC outputs |
| Sample preparation | Independent-unit counts, batch/group composition, explicit paired/confounded decisions and exact model/plot sample tables |
| Annotation preparation | Local mapping exports and GMT converted to bounded tables; duplicate counts, ambiguity and resource identities retained |
| Interpretation | Microarray-to-mapping/ORA/GSEA handoff with explicit statistic and direction; sample-correlation figure; probe-aware source-bound report text |
| Workflow | Fourteen checked native formats, including existing DESeq2; original scientific package remains unchanged; two expression templates |
| Installation | Existing bundles extended; precise microarray R/limma dependency inventory |

Start with [expression workflows](expression-workflows.md) and the [small original example](../examples/expression/README.md). Tests cover actual small helper fits and handoffs plus input, invalidation and resource-identity regressions. Scope remains bounded: no formal Agent comparison, representative scientific benchmark or human expert review. Public matrices with unresolved scales and sample semantics remain incomplete rather than being forced into a model.

The earlier expansion and workflow stages are retained in project history. This stage changes five existing packages and adds one; the other 51 package identities remain unchanged. The optional companion still never executes a plan, downloads data or installs tools. Large h5ad support, paired expression models, qPCR and microbiome group inference remain future work.
