# 23-Skill catalog

The current release contains 23 independently installable `preview + reviewed` Skills across 11 Domains and 15 Clusters. [registry.json](../registry.json) is the authoritative versioned index; this page explains the research organization and routing surface.

```text
11 Domains
  -> 15 Clusters
    -> 23 one-job Skills
```

Every Skill uses the same lightweight interaction boundary:

- inspect safely discoverable facts first;
- ask exactly one recommended question at a time only when an unresolved choice would change the result;
- use a provider-neutral core;
- treat an explicit request as authorization for the matching bounded public read and requested download;
- use the shared companion anonymously; treat any authenticated host adapter as a separately disclosed boundary;
- confirm sensitive uploads, remote jobs, unrequested bulk expansion, or terms-restricted access; paid and metered providers are absent;
- claim `completed` only for checked live responses with provenance, keep incomplete work partial, and report blocked or failed calls honestly. The shared companion supports `GET`/`HEAD`; conditional jobs require a reviewed host adapter or return `needs-tool`.

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 1 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `bioinformatics-format-and-identifier-validation` | `preview + reviewed` (`0.4.0`) |
| 2 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `scientific-file-preflight-and-resource-planning` | `preview + reviewed` (`0.4.0`) |
| 3 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `biological-database-record-retrieval-and-identifier-resolution` | `preview + reviewed` (`0.4.0`) |
| 4 | D01 Data & Workflow Foundations | C02 Execution and provenance | `environment-and-provenance-capture` | `preview + reviewed` (`0.4.0`) |
| 5 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-io-and-transformation` | `preview + reviewed` (`0.4.0`) |
| 6 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-similarity-and-homology-search` | `preview + reviewed` (`0.4.0`) |
| 7 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `pairwise-and-multiple-sequence-alignment` | `preview + reviewed` (`0.4.0`) |
| 8 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `alignment-file-operations` | `preview + reviewed` (`0.4.0`) |
| 9 | D02 Sequence, Reads, Genomes & Evolution | C06 Genome coordinates | `genomic-interval-operations` | `preview + reviewed` (`0.4.0`) |
| 10 | D03 Variant, Population & Causal Genomics | C10 Variant representation and cohorts | `vcf-normalization-qc-and-query` | `preview + reviewed` (`0.4.0`) |
| 11 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `count-based-differential-expression` | `preview + reviewed` (`0.4.0`) |
| 12 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-object-io-and-qc` | `preview + reviewed` (`0.4.0`) |
| 13 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-core-analysis` | `preview + reviewed` (`0.4.0`) |
| 14 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | `proteomics-quantification-table-qc` | `preview + reviewed` (`0.4.0`) |
| 15 | D09 Protein Structure & Molecular Biophysics | C25 Structure evidence | `protein-structure-retrieval-and-comparison` | `preview + reviewed` (`0.4.0`) |
| 16 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `molecule-standardization-and-descriptors` | `preview + reviewed` (`0.4.0`) |
| 17 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `chemical-similarity-and-substructure-search` | `preview + reviewed` (`0.4.0`) |
| 18 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `over-representation-analysis` | `preview + reviewed` (`0.4.0`) |
| 19 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `ranked-gene-set-enrichment` | `preview + reviewed` (`0.4.0`) |
| 20 | D12 Study Design & Biostatistics | C34 Experimental design | `experimental-design-power-and-batch-planning` | `preview + reviewed` (`0.4.0`) |
| 21 | D12 Study Design & Biostatistics | C35 Statistical inference | `statistical-analysis-and-multiple-testing` | `preview + reviewed` (`0.4.0`) |
| 22 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `biomedical-literature-and-public-study-search` | `preview + reviewed` (`0.4.0`) |
| 23 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `evidence-synthesis-and-research-traceability` | `preview + reviewed` (`0.4.0`) |

All 23 exact packages appear under `skills/<slug>/` and in `registry.json`. Their current state means reviewed and installable, not runtime-validated, scientifically proven, clinically authorized, or better than a baseline. `Stable` is allowed only with bounded `evaluated` assurance.

D06 epigenomics/perturbation and D07 microbiome/pathogens remain later-wave research areas. D08 is represented only by proteomics quantification-table QC; raw-MS processing, broader proteomics workflows, metabolomics, and cytometry remain later-wave work.
