# Goose Bio Skills catalog

The checked-out preview contains **60 independently installable Skills**, with **43 bounded helpers**, across 13 Domains and 27 Clusters. All packages remain `preview + reviewed`. The immutable collection release is v0.9.0; `registry.json` defines current package versions and exact digests. Merging to main does not create a tagged collection release or change assurance.

Start with [task bundles](task-bundles.md) for a research task, or use the complete list below. Install the whole package directory. A helper covers only its declared input and method; the wider Skill may still need an external tool or a scientific decision.

| # | Domain | Cluster | Skill | Package version | Bundled helper |
| ---: | --- | --- | --- | --- | --- |
| 1 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [bioinformatics-format-and-identifier-validation](../skills/bioinformatics-format-and-identifier-validation/SKILL.md) | 0.12.0 | Yes |
| 2 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [biological-database-record-retrieval-and-identifier-resolution](../skills/biological-database-record-retrieval-and-identifier-resolution/SKILL.md) | 0.12.0 | Yes |
| 3 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [public-expression-dataset-preparation](../skills/public-expression-dataset-preparation/SKILL.md) | 0.11.0 | Yes |
| 4 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [public-sequencing-run-manifest-retrieval](../skills/public-sequencing-run-manifest-retrieval/SKILL.md) | 0.10.0 | No |
| 5 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [scientific-file-preflight-and-resource-planning](../skills/scientific-file-preflight-and-resource-planning/SKILL.md) | 0.10.0 | Yes |
| 6 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | [taxonomy-name-and-taxid-resolution](../skills/taxonomy-name-and-taxid-resolution/SKILL.md) | 0.10.0 | No |
| 7 | D01 Data & Workflow Foundations | C02 Execution and provenance | [environment-and-provenance-capture](../skills/environment-and-provenance-capture/SKILL.md) | 0.10.0 | No |
| 8 | D01 Data & Workflow Foundations | C03 Reporting and visualization | [bioinformatics-qc-and-publication-reporting](../skills/bioinformatics-qc-and-publication-reporting/SKILL.md) | 0.15.0 | Yes |
| 9 | D01 Data & Workflow Foundations | C03 Reporting and visualization | [bioinformatics-result-visualization](../skills/bioinformatics-result-visualization/SKILL.md) | 0.15.0 | Yes |
| 10 | D01 Data & Workflow Foundations | C03 Reporting and visualization | [multi-comparison-result-concordance](../skills/multi-comparison-result-concordance/SKILL.md) | 0.11.0 | Yes |
| 11 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | [pairwise-and-multiple-sequence-alignment](../skills/pairwise-and-multiple-sequence-alignment/SKILL.md) | 0.10.0 | No |
| 12 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | [sequence-io-and-transformation](../skills/sequence-io-and-transformation/SKILL.md) | 0.10.0 | No |
| 13 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | [sequence-similarity-and-homology-search](../skills/sequence-similarity-and-homology-search/SKILL.md) | 0.10.0 | No |
| 14 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | [alignment-file-operations](../skills/alignment-file-operations/SKILL.md) | 0.10.0 | No |
| 15 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | [raw-read-quality-reporting](../skills/raw-read-quality-reporting/SKILL.md) | 0.11.0 | Yes |
| 16 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | [raw-read-trimming-and-filtering](../skills/raw-read-trimming-and-filtering/SKILL.md) | 0.10.0 | No |
| 17 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | [read-alignment-selection-and-execution](../skills/read-alignment-selection-and-execution/SKILL.md) | 0.10.0 | Yes |
| 18 | D02 Sequence, Reads, Genomes & Evolution | C06 Genome coordinates | [genomic-interval-operations](../skills/genomic-interval-operations/SKILL.md) | 0.15.0 | Yes |
| 19 | D02 Sequence, Reads, Genomes & Evolution | C07 Gene models and annotation | [gff-gtf-gene-model-qc](../skills/gff-gtf-gene-model-qc/SKILL.md) | 0.10.0 | Yes |
| 20 | D02 Sequence, Reads, Genomes & Evolution | C08 Comparative and evolutionary genomics | [phylogenetic-tree-io-and-qc](../skills/phylogenetic-tree-io-and-qc/SKILL.md) | 0.10.0 | Yes |
| 21 | D02 Sequence, Reads, Genomes & Evolution | C08 Comparative and evolutionary genomics | [public-orthology-retrieval-and-qc](../skills/public-orthology-retrieval-and-qc/SKILL.md) | 0.10.0 | No |
| 22 | D03 Variant, Population & Causal Genomics | C10 Variant representation and cohorts | [vcf-normalization-qc-and-query](../skills/vcf-normalization-qc-and-query/SKILL.md) | 0.10.0 | No |
| 23 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | [bulk-rnaseq-gene-count-matrix-assembly](../skills/bulk-rnaseq-gene-count-matrix-assembly/SKILL.md) | 0.10.0 | Yes |
| 24 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | [bulk-rnaseq-gene-counting-from-alignment](../skills/bulk-rnaseq-gene-counting-from-alignment/SKILL.md) | 0.10.0 | Yes |
| 25 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | [count-based-differential-expression](../skills/count-based-differential-expression/SKILL.md) | 0.10.0 | Yes |
| 26 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | [normalized-microarray-differential-expression](../skills/normalized-microarray-differential-expression/SKILL.md) | 0.12.0 | Yes |
| 27 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | [qpcr-relative-expression-and-qc](../skills/qpcr-relative-expression-and-qc/SKILL.md) | 0.14.0 | Yes |
| 28 | D04 Bulk & Specialized Transcriptomics | C13 Splicing and isoforms | [junction-psi-and-delta-analysis](../skills/junction-psi-and-delta-analysis/SKILL.md) | 0.10.0 | Yes |
| 29 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | [single-cell-core-analysis](../skills/single-cell-core-analysis/SKILL.md) | 0.11.0 | Yes |
| 30 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | [single-cell-marker-evidence-review](../skills/single-cell-marker-evidence-review/SKILL.md) | 0.11.0 | Yes |
| 31 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | [single-cell-object-io-and-qc](../skills/single-cell-object-io-and-qc/SKILL.md) | 0.11.0 | Yes |
| 32 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | [single-cell-pseudobulk-aggregation](../skills/single-cell-pseudobulk-aggregation/SKILL.md) | 0.11.0 | Yes |
| 33 | D06 Epigenomics, Regulation & Perturbation | C16 Chromatin interval evidence | [chromatin-peak-set-qc](../skills/chromatin-peak-set-qc/SKILL.md) | 0.10.0 | Yes |
| 34 | D07 Microbiome, Metagenomics & Pathogens | C18 Amplicon feature tables | [amplicon-feature-table-and-taxonomy-qc](../skills/amplicon-feature-table-and-taxonomy-qc/SKILL.md) | 0.10.0 | Yes |
| 35 | D07 Microbiome, Metagenomics & Pathogens | C20 Community diversity | [amplicon-alpha-diversity-analysis](../skills/amplicon-alpha-diversity-analysis/SKILL.md) | 0.10.0 | Yes |
| 36 | D07 Microbiome, Metagenomics & Pathogens | C20 Community diversity | [amplicon-beta-diversity-distance-analysis](../skills/amplicon-beta-diversity-distance-analysis/SKILL.md) | 0.10.0 | Yes |
| 37 | D07 Microbiome, Metagenomics & Pathogens | C20 Community diversity | [distance-matrix-principal-coordinates-analysis](../skills/distance-matrix-principal-coordinates-analysis/SKILL.md) | 0.13.0 | Yes |
| 38 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | [protein-level-differential-abundance](../skills/protein-level-differential-abundance/SKILL.md) | 0.13.0 | Yes |
| 39 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | [proteomics-quantification-table-qc](../skills/proteomics-quantification-table-qc/SKILL.md) | 0.13.0 | Yes |
| 40 | D08 Proteomics, Metabolomics & Cytometry | C23 Metabolomics feature tables | [untargeted-metabolomics-feature-table-qc](../skills/untargeted-metabolomics-feature-table-qc/SKILL.md) | 0.10.0 | Yes |
| 41 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | [fcs-file-io-and-metadata-qc](../skills/fcs-file-io-and-metadata-qc/SKILL.md) | 0.10.0 | No |
| 42 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | [flow-cytometry-arcsinh-transformation](../skills/flow-cytometry-arcsinh-transformation/SKILL.md) | 0.10.0 | Yes |
| 43 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | [flow-cytometry-compensation-application](../skills/flow-cytometry-compensation-application/SKILL.md) | 0.10.0 | Yes |
| 44 | D09 Protein Structure & Molecular Biophysics | C25 Structure evidence | [protein-structure-retrieval-and-comparison](../skills/protein-structure-retrieval-and-comparison/SKILL.md) | 0.10.0 | No |
| 45 | D09 Protein Structure & Molecular Biophysics | C27 Interfaces and dynamics | [protein-interface-contact-analysis](../skills/protein-interface-contact-analysis/SKILL.md) | 0.10.0 | Yes |
| 46 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | [chemical-similarity-and-substructure-search](../skills/chemical-similarity-and-substructure-search/SKILL.md) | 0.10.0 | No |
| 47 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | [molecule-standardization-and-descriptors](../skills/molecule-standardization-and-descriptors/SKILL.md) | 0.10.0 | No |
| 48 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | [over-representation-analysis](../skills/over-representation-analysis/SKILL.md) | 0.10.0 | Yes |
| 49 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | [ranked-gene-set-enrichment](../skills/ranked-gene-set-enrichment/SKILL.md) | 0.12.0 | Yes |
| 50 | D12 Study Design & Biostatistics | C34 Experimental design | [experimental-design-power-and-batch-planning](../skills/experimental-design-power-and-batch-planning/SKILL.md) | 0.10.0 | No |
| 51 | D12 Study Design & Biostatistics | C35 Statistical inference | [correlation-and-association-screening](../skills/correlation-and-association-screening/SKILL.md) | 0.11.0 | Yes |
| 52 | D12 Study Design & Biostatistics | C35 Statistical inference | [independent-2x2-categorical-comparison](../skills/independent-2x2-categorical-comparison/SKILL.md) | 0.14.0 | Yes |
| 53 | D12 Study Design & Biostatistics | C35 Statistical inference | [missing-data-and-sensitivity-analysis](../skills/missing-data-and-sensitivity-analysis/SKILL.md) | 0.10.0 | Yes |
| 54 | D12 Study Design & Biostatistics | C35 Statistical inference | [statistical-analysis-and-multiple-testing](../skills/statistical-analysis-and-multiple-testing/SKILL.md) | 0.10.0 | Yes |
| 55 | D12 Study Design & Biostatistics | C35 Statistical inference | [two-group-comparison-and-effect-estimation](../skills/two-group-comparison-and-effect-estimation/SKILL.md) | 0.11.0 | Yes |
| 56 | D12 Study Design & Biostatistics | C36 Survival analysis | [kaplan-meier-survival-analysis](../skills/kaplan-meier-survival-analysis/SKILL.md) | 0.10.0 | Yes |
| 57 | D12 Study Design & Biostatistics | C36 Survival analysis | [two-group-log-rank-survival-comparison](../skills/two-group-log-rank-survival-comparison/SKILL.md) | 0.10.0 | Yes |
| 58 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | [biomedical-literature-and-public-study-search](../skills/biomedical-literature-and-public-study-search/SKILL.md) | 0.10.0 | No |
| 59 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | [evidence-synthesis-and-research-traceability](../skills/evidence-synthesis-and-research-traceability/SKILL.md) | 0.10.0 | No |
| 60 | D13 Biomedical Evidence & Clinical Interpretation | C38 Variant evidence | [human-variant-evidence-retrieval](../skills/human-variant-evidence-retrieval/SKILL.md) | 0.10.0 | Yes |

## Scope and history

Facts come before questions. Inspect available inputs, ask one result-changing question when necessary, and preserve unresolved decisions and incomplete outcomes. Network execution requires the separately reviewed connector or host adapter; installing a package does not install that connector. See the [integration contract](integration-contract.md).

The immutable v0.9.0 collection has 48 packages. The subsequent efficiency preview added figures and reporting; the practical expansion added six jobs and enhanced six existing packages. See [current upgrade notes](unreleased-upgrade.md) and [historical upgrade notes](upgrade-history-2026-09-10.md). Historical fixtures remain intact; they do not evaluate later agent behavior.
