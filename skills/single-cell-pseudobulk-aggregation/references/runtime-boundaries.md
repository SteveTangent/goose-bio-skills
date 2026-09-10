# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution; AnnData 0.13.3.post0 / h5py 3.16.0 small h5ad execution.

Inputs: Small h5ad counts layer, biological sample_id and reviewed cell_type; samples.tsv sample_id/condition; one type, min-cells and contrast.

Outputs: New counts.tsv and samples.tsv plus aggregation.json with count conservation, cell counts, exclusions and downstream readiness.

Unsupported: Paired/longitudinal designs, normalized-count summation, condition DE, automatic labels and multiple-cell-type inference.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
