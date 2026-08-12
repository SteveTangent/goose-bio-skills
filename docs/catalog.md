# Research catalog: 29-Skill Beta plus 3 candidates

The verified `main` Beta contains 29 independently installable `preview + reviewed` Skills across 11 Domains and 17 Clusters. The `research` branch adds three Wave R1 candidates, for 32 branch packages across 11 Domains and 19 Clusters. [registry.json](../registry.json) is the authoritative index for the checked-out branch; a research entry is not a `main` promotion.

```text
11 Domains
  -> 19 Clusters on research
    -> 29 Beta Skills + 3 research candidates
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
| 1 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `bioinformatics-format-and-identifier-validation` | `preview + reviewed` (`0.6.0`) |
| 2 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `scientific-file-preflight-and-resource-planning` | `preview + reviewed` (`0.6.0`) |
| 3 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `biological-database-record-retrieval-and-identifier-resolution` | `preview + reviewed` (`0.6.0`) |
| 4 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `taxonomy-name-and-taxid-resolution` | `preview + reviewed` (`0.6.0`) |
| 5 | D01 Data & Workflow Foundations | C01 Data intake, validation, and public records | `public-sequencing-run-manifest-retrieval` | `preview + reviewed` (`0.6.0`) |
| 6 | D01 Data & Workflow Foundations | C02 Execution and provenance | `environment-and-provenance-capture` | `preview + reviewed` (`0.6.0`) |
| 7 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-io-and-transformation` | `preview + reviewed` (`0.6.0`) |
| 8 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `sequence-similarity-and-homology-search` | `preview + reviewed` (`0.6.0`) |
| 9 | D02 Sequence, Reads, Genomes & Evolution | C04 Sequence objects and homology | `pairwise-and-multiple-sequence-alignment` | `preview + reviewed` (`0.6.0`) |
| 10 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `raw-read-quality-reporting` | `preview + reviewed` (`0.6.0`) |
| 11 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `raw-read-trimming-and-filtering` | `preview + reviewed` (`0.6.0`) |
| 12 | D02 Sequence, Reads, Genomes & Evolution | C05 Read preprocessing and alignment | `alignment-file-operations` | `preview + reviewed` (`0.6.0`) |
| 13 | D02 Sequence, Reads, Genomes & Evolution | C06 Genome coordinates | `genomic-interval-operations` | `preview + reviewed` (`0.6.0`) |
| 14 | D02 Sequence, Reads, Genomes & Evolution | C07 Gene models and annotation | `gff-gtf-gene-model-qc` | `preview + reviewed` (`0.6.0`) |
| 15 | D03 Variant, Population & Causal Genomics | C10 Variant representation and cohorts | `vcf-normalization-qc-and-query` | `preview + reviewed` (`0.6.0`) |
| 16 | D04 Bulk & Specialized Transcriptomics | C12 Bulk expression pipeline | `count-based-differential-expression` | `preview + reviewed` (`0.6.0`) |
| 17 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-object-io-and-qc` | `preview + reviewed` (`0.6.0`) |
| 18 | D05 Single-cell & Spatial Omics | C14 Object, QC and core analysis | `single-cell-core-analysis` | `preview + reviewed` (`0.6.0`) |
| 19 | D08 Proteomics, Metabolomics & Cytometry | C22 Quantitative proteomics | `proteomics-quantification-table-qc` | `preview + reviewed` (`0.6.0`) |
| 20 | D08 Proteomics, Metabolomics & Cytometry | C24 Cytometry file standards | `fcs-file-io-and-metadata-qc` | `preview + reviewed` (`0.6.0`) |
| 21 | D09 Protein Structure & Molecular Biophysics | C25 Structure evidence | `protein-structure-retrieval-and-comparison` | `preview + reviewed` (`0.6.0`) |
| 22 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `molecule-standardization-and-descriptors` | `preview + reviewed` (`0.6.0`) |
| 23 | D10 Cheminformatics & Drug Discovery | C28 Molecule curation and search | `chemical-similarity-and-substructure-search` | `preview + reviewed` (`0.6.0`) |
| 24 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `over-representation-analysis` | `preview + reviewed` (`0.6.0`) |
| 25 | D11 Functional Interpretation, Networks & Multiomics | C31 Gene-set enrichment | `ranked-gene-set-enrichment` | `preview + reviewed` (`0.6.0`) |
| 26 | D12 Study Design & Biostatistics | C34 Experimental design | `experimental-design-power-and-batch-planning` | `preview + reviewed` (`0.6.0`) |
| 27 | D12 Study Design & Biostatistics | C35 Statistical inference | `statistical-analysis-and-multiple-testing` | `preview + reviewed` (`0.6.0`) |
| 28 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `biomedical-literature-and-public-study-search` | `preview + reviewed` (`0.6.0`) |
| 29 | D13 Biomedical Evidence & Clinical Interpretation | C37 Literature and public studies | `evidence-synthesis-and-research-traceability` | `preview + reviewed` (`0.6.0`) |

## Wave R1 research candidates

| Candidate | Domain | Cluster | Skill | Branch state |
| ---: | --- | --- | --- | --- |
| R1-1 | D12 Study Design & Biostatistics | C35 Statistical inference | `missing-data-and-sensitivity-analysis` | `research`; not promoted |
| R1-2 | D09 Protein Structure & Molecular Biophysics | C27 Interfaces and dynamics | `protein-interface-contact-analysis` | `research`; not promoted |
| R1-3 | D02 Sequence, Reads, Genomes & Evolution | C08 Comparative and evolutionary genomics | `public-orthology-retrieval-and-qc` | `research`; not promoted |

All 32 exact research-branch packages appear under `skills/<slug>/` and in `registry.json`. The first 29 form the verified Beta baseline; the three Wave R1 packages remain candidates until [their promotion gates](research-skill-promotion-gates.md) pass. `Preview + reviewed` means a package boundary was reviewed, not that runtime, scientific validity, clinical use, or superiority over a baseline was established. `Stable` is allowed only with bounded `evaluated` assurance.

D06 epigenomics/perturbation and D07 microbiome/pathogens remain later-wave research areas. D08 now includes bounded proteomics-table and FCS metadata QC; raw-MS processing, broader proteomics workflows, metabolomics, compensation, and gating remain later-wave work.
