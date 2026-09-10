# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: LABEL=TSV tables with feature_id, effect, padj, tested; shared taxon, namespace, effect scale, direction and thresholds.

Outputs: JSON with explicit not-present/not-tested/tested-not-selected/selected states, direction and common-tested-universe Jaccard.

Unsupported: Meta-analysis, p-value combination, harmonizing incompatible scales or automatic biological ID mapping.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
