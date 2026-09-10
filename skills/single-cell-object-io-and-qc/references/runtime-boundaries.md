# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution; AnnData 0.13.3.post0 / h5py 3.16.0 small h5ad execution.

Inputs: Small h5ad; named raw-count layer, sample column, RNA assay, explicit min-counts/min-genes; optional mitochondrial prefix/fraction.

Outputs: New checked.h5ad, per-cell qc.tsv and qc.json including exact output hash for the core-analysis handoff.

Unsupported: Seurat execution/conversion, doublet detection, ambient-RNA correction, automatic cutoffs, integration and annotation.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
