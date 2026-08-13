# Bio 02 catalog: 48-Skill Beta

The v0.9.0 `main` Beta contains 48 independently installable `preview + reviewed` Skills across 13 Domains and 26 Clusters. [registry.json](../registry.json) is authoritative for the checked-out branch. Wave R5 entered at the same assurance level; this is not an upgrade to evaluated or stable assurance.

```text
13 Domains in v0.9.0
  -> 26 Clusters
    -> 48 main Beta Skills
```

Every Skill uses the same lightweight interaction boundary:

- inspect safely discoverable facts first;
- ask exactly one recommended question at a time only when an unresolved choice would change the result;
- use a provider-neutral core;
- treat an explicit request as authorization for the matching bounded public read and requested download;
- use the shared companion anonymously; treat any authenticated host adapter as a separately disclosed boundary;
- never upload patient data, protected health information, controlled-access data, credentials, or secrets; confirm other non-prohibited sensitive uploads, remote jobs, unrequested bulk expansion, or terms-restricted access; paid and metered providers are absent;
- claim `completed` only for checked live responses with provenance, keep incomplete work partial, and report blocked or failed calls honestly. The shared companion supports `GET`/`HEAD`; conditional jobs require a reviewed host adapter or return `needs-tool`.

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 1 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `bioinformatics-format-and-identifier-validation` | `preview + reviewed` (`0.9.0`) |
| 2 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `scientific-file-preflight-and-resource-planning` | `preview + reviewed` (`0.9.0`) |
| 3 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `biological-database-record-retrieval-and-identifier-resolution` | `preview + reviewed` (`0.9.0`) |
| 4 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `taxonomy-name-and-taxid-resolution` | `preview + reviewed` (`0.9.0`) |
| 5 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `public-sequencing-run-manifest-retrieval` | `preview + reviewed` (`0.9.0`) |
| 6 | D01 Data & Workflow Foundations | C02 Execution and provenance | `environment-and-provenance-capture` | `preview + reviewed` (`0.9.0`) |
| 7 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-io-and-transformation` | `preview + reviewed` (`0.9.0`) |
| 8 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-similarity-and-homology-search` | `preview + reviewed` (`0.9.0`) |
| 9 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `pairwise-and-multiple-sequence-alignment` | `preview + reviewed` (`0.9.0`) |
| 10 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `raw-read-quality-reporting` | `preview + reviewed` (`0.9.0`) |
| 11 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `raw-read-trimming-and-filtering` | `preview + reviewed` (`0.9.0`) |
| 12 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `alignment-file-operations` | `preview + reviewed` (`0.9.0`) |
| 13 | D02 Sequence, Reads, Genomes & Evolution | C06 Genome coordinates | `genomic-interval-operations` | `preview + reviewed` (`0.9.0`) |
| 14 | D02 Sequence, Reads, Genomes & Evolution | C07 Gene models and annotation | `gff-gtf-gene-model-qc` | `preview + reviewed` (`0.9.0`) |
| 15 | D03 Variant, Population & Causal Genomics | C10 Variant representation and cohorts | `vcf-normalization-qc-and-query` | `preview + reviewed` (`0.9.0`) |
| 16 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `count-based-differential-expression` | `preview + reviewed` (`0.9.0`) |
| 17 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-object-io-and-qc` | `preview + reviewed` (`0.9.0`) |
| 18 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-core-analysis` | `preview + reviewed` (`0.9.0`) |
| 19 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | `proteomics-quantification-table-qc` | `preview + reviewed` (`0.9.0`) |
| 20 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | `fcs-file-io-and-metadata-qc` | `preview + reviewed` (`0.9.0`) |
| 21 | D09 Protein Structure & Molecular Biophysics | C25 Structure evidence | `protein-structure-retrieval-and-comparison` | `preview + reviewed` (`0.9.0`) |
| 22 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `molecule-standardization-and-descriptors` | `preview + reviewed` (`0.9.0`) |
| 23 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `chemical-similarity-and-substructure-search` | `preview + reviewed` (`0.9.0`) |
| 24 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `over-representation-analysis` | `preview + reviewed` (`0.9.0`) |
| 25 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `ranked-gene-set-enrichment` | `preview + reviewed` (`0.9.0`) |
| 26 | D12 Study Design & Biostatistics | C34 Experimental design | `experimental-design-power-and-batch-planning` | `preview + reviewed` (`0.9.0`) |
| 27 | D12 Study Design & Biostatistics | C35 Statistical inference | `statistical-analysis-and-multiple-testing` | `preview + reviewed` (`0.9.0`) |
| 28 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `biomedical-literature-and-public-study-search` | `preview + reviewed` (`0.9.0`) |
| 29 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `evidence-synthesis-and-research-traceability` | `preview + reviewed` (`0.9.0`) |

## Wave R1 additions in v0.7.0

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 30 | D12 Study Design & Biostatistics | C35 Statistical inference | `missing-data-and-sensitivity-analysis` | `preview + reviewed` (`0.9.0`) |
| 31 | D09 Protein Structure & Molecular Biophysics | C27 Interfaces and dynamics | `protein-interface-contact-analysis` | `preview + reviewed` (`0.9.0`) |
| 32 | D02 Sequence, Reads, Genomes & Evolution | C08 Comparative and evolutionary genomics | `public-orthology-retrieval-and-qc` | `preview + reviewed` (`0.9.0`) |

## Wave R2 additions in v0.8.0

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 33 | D07 Microbiome, Metagenomics & Pathogens | C18 Amplicon feature tables | `amplicon-feature-table-and-taxonomy-qc` | `preview + reviewed` (`0.9.0`) |
| 34 | D06 Epigenomics, Regulation & Perturbation | C16 Chromatin interval evidence | `chromatin-peak-set-qc` | `preview + reviewed` (`0.9.0`) |
| 35 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | `protein-level-differential-abundance` | `preview + reviewed` (`0.9.0`) |

## Wave R3 additions in v0.8.0

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 36 | D02 Sequence, Reads, Genomes & Evolution | C08 Comparative and evolutionary genomics | `phylogenetic-tree-io-and-qc` | `preview + reviewed` (`0.9.0`) |
| 37 | D08 Proteomics, Metabolomics & Cytometry | C23 Metabolomics feature tables | `untargeted-metabolomics-feature-table-qc` | `preview + reviewed` (`0.9.0`) |
| 38 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `read-alignment-selection-and-execution` | `preview + reviewed` (`0.9.0`); point-in-time synthetic real-minimap2 canary passed |

## Wave R4 additions in v0.8.0

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 39 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `bulk-rnaseq-gene-counting-from-alignment` | `preview + reviewed` (`0.9.0`) |
| 40 | D04 Bulk & Specialized Transcriptomics | C13 Splicing and isoforms | `junction-psi-and-delta-analysis` | `preview + reviewed` (`0.9.0`) |
| 41 | D07 Microbiome, Metagenomics & Pathogens | C20 Community diversity | `amplicon-alpha-diversity-analysis` | `preview + reviewed` (`0.9.0`) |
| 42 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | `flow-cytometry-compensation-application` | `preview + reviewed` (`0.9.0`) |
| 43 | D12 Study Design & Biostatistics | C36 Survival analysis | `kaplan-meier-survival-analysis` | `preview + reviewed` (`0.9.0`) |
| 44 | D13 Biomedical Evidence & Clinical Interpretation | C38 Variant evidence | `human-variant-evidence-retrieval` | `preview + reviewed` (`0.9.0`) |

The first 32 packages came from the v0.7.0 Beta; the 12 Wave R2/R3/R4 packages entered through the [promotion gates](research-skill-promotion-gates.md) and the v0.8.0 atomic release. All 44 were mechanically rebound to v0.9.0 with rollback to v0.8.0. `Preview + reviewed` means a package boundary was reviewed, not that runtime, scientific validity, clinical use, or superiority over a baseline was established. `Stable` is allowed only with bounded `evaluated` assurance.

## Wave R5 additions in v0.9.0

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 45 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `bulk-rnaseq-gene-count-matrix-assembly` | `preview + reviewed` (`0.9.0`) |
| 46 | D07 Microbiome, Metagenomics & Pathogens | C20 Community diversity | `amplicon-beta-diversity-distance-analysis` | `preview + reviewed` (`0.9.0`) |
| 47 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | `flow-cytometry-arcsinh-transformation` | `preview + reviewed` (`0.9.0`) |
| 48 | D12 Study Design & Biostatistics | C36 Survival analysis | `two-group-log-rank-survival-comparison` | `preview + reviewed` (`0.9.0`) |

These four exact packages are bound by the Wave R5 fixture, package digests,
deterministic replay, and independent route-selection diagnostic. Promotion to
`main` does not constitute formal agent-runtime or scientific evaluation,
representative benchmarking, or human-expert review.

D06 and D07 now include narrow peak-set and amplicon-table QC Skills. Wave R3 added local Newick QC, metabolomics feature-table QC, and one fixed short-DNA alignment branch. Wave R4 added bounded counting, PSI, alpha diversity, compensation, Kaplan–Meier, and exact-ID variant-evidence jobs. Wave R5 adds count-matrix assembly, two descriptive beta-diversity distances, one fixed two-group log-rank comparison, and explicit-cofactor arcsinh transformation. Peak calling, pathogen interpretation, raw-MS processing, broader proteomics, multi-aligner selection, gating, and clinical classification remain later-wave work.
