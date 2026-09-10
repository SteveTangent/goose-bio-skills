# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution; AnnData 0.13.3.post0 / h5py 3.16.0 small h5ad execution; Scanpy 1.12.4 / igraph 0.11.9 CPU smoke.

Inputs: Checked h5ad and matching qc.json; preserved counts layer; explicit HVG/PCA/neighbors/resolution/seed settings.

Outputs: Processed object, embedding.tsv, descriptive cluster-vs-rest markers.tsv and analysis.json with actual settings/versions.

Unsupported: Batch integration, automatic annotation, trajectory/velocity, GPU/distributed workflows and condition-level DE.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
