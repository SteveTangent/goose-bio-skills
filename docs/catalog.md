# 20-Skill catalog

The first research wave contains 20 independently installable `preview + reviewed` Skills across 10 Domains and 14 Clusters. [registry.json](../registry.json) is the authoritative versioned index; this page explains the research organization and routing surface.

```text
10 Domains
  -> 14 Clusters
    -> 20 one-job Skills
```

Every Skill uses the same lightweight interaction boundary:

- inspect safely discoverable facts first;
- ask exactly one recommended question at a time only when an unresolved choice would change the result;
- use a provider-neutral core;
- in phase 1, disclose an optional connector and issue a `confirmation_token` without reading configuration;
- in phase 2, read a user- or host-provided local JSON configuration only with both `--acknowledge <exact-confirmation-token>` and `--config <path>`;
- missing/mismatched acknowledgement returns `needs-user-confirmation` without reading configuration; after acknowledgement, missing config or credentials returns `needs-user-config` or `needs-credential`; `config-validated` still means zero-network plan-only.

| Order | Domain | Cluster | Skill | Public state |
| ---: | --- | --- | --- | --- |
| 1 | D01 Data & Workflow Foundations | C01 Data intake and validation | `bioinformatics-format-and-identifier-validation` | `preview + reviewed` (`0.2.1`) |
| 2 | D01 Data & Workflow Foundations | C02 Execution and provenance | `environment-and-provenance-capture` | `preview + reviewed` (`0.2.1`) |
| 3 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-io-and-transformation` | `preview + reviewed` (`0.2.1`) |
| 4 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-similarity-and-homology-search` | `preview + reviewed` (`0.2.1`) |
| 5 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `pairwise-and-multiple-sequence-alignment` | `preview + reviewed` (`0.2.1`) |
| 6 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `alignment-file-operations` | `preview + reviewed` (`0.2.1`) |
| 7 | D02 Sequence, Reads, Genomes & Evolution | C06 Genome coordinates | `genomic-interval-operations` | `preview + reviewed` (`0.2.1`) |
| 8 | D03 Variant, Population & Causal Genomics | C10 Variant representation and cohorts | `vcf-normalization-qc-and-query` | `preview + reviewed` (`0.2.1`) |
| 9 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `count-based-differential-expression` | `preview + reviewed` (`0.2.1`) |
| 10 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-object-io-and-qc` | `preview + reviewed` (`0.2.1`) |
| 11 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-core-analysis` | `preview + reviewed` (`0.2.1`) |
| 12 | D09 Protein Structure & Molecular Biophysics | C25 Structure evidence | `protein-structure-retrieval-and-comparison` | `preview + reviewed` (`0.2.1`) |
| 13 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `molecule-standardization-and-descriptors` | `preview + reviewed` (`0.2.1`) |
| 14 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `chemical-similarity-and-substructure-search` | `preview + reviewed` (`0.2.1`) |
| 15 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `over-representation-analysis` | `preview + reviewed` (`0.2.1`) |
| 16 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `ranked-gene-set-enrichment` | `preview + reviewed` (`0.2.1`) |
| 17 | D12 Study Design & Biostatistics | C34 Experimental design | `experimental-design-power-and-batch-planning` | `preview + reviewed` (`0.2.1`) |
| 18 | D12 Study Design & Biostatistics | C35 Statistical inference | `statistical-analysis-and-multiple-testing` | `preview + reviewed` (`0.2.1`) |
| 19 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `biomedical-literature-and-public-study-search` | `preview + reviewed` (`0.2.1`) |
| 20 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `evidence-synthesis-and-research-traceability` | `preview + reviewed` (`0.2.1`) |

All 20 exact packages appear under `skills/<slug>/` and in `registry.json`. Their current state means reviewed and installable, not runtime-validated, scientifically proven, clinically authorized, or better than a baseline. `Stable` is allowed only with bounded `evaluated` assurance.

D06 epigenomics/perturbation, D07 microbiome/pathogens, and D08 proteomics/metabolomics/cytometry remain later-wave research areas; they are not installable packages in this release.
