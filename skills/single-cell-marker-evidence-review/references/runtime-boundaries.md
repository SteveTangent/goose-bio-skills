# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: Marker TSV cluster/gene_id/score/padj; reference TSV taxon/tissue/namespace/cell_type/gene_id/role (support or conflict); optional measured mean_expression/fraction_expressing.

Outputs: JSON with supporting/conflicting genes, coverage, candidates, ambiguous/unknown states and untouched original clusters.

Unsupported: Automatic final labels, reference downloads, cross-species mapping, atlas integration and diagnostic classification.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
