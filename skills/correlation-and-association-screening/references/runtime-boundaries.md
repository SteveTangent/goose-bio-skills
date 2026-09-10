# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution.

Inputs: Wide numeric TSV with unique sample_id; pairs TSV with x and y; method, inference, scale and missing policy; independent units.

Outputs: JSON with coefficient, effective n, excluded sample IDs, optional permutation p-values and undefined constant-pair states.

Unsupported: Automatic all-pairs mining, batch adjustment, repeated measures, partial correlation and causal inference.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
