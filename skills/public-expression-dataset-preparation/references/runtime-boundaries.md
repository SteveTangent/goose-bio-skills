# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: One GSE; bounded downloaded Series Matrix with ID_REF; selected GPL; declared scale (unknown allowed); optional curated sample_id/condition table.

Outputs: New expression.tsv, features.tsv, samples.tsv, original-samples.tsv and preparation.json; unresolved scale/groups remain needs-decision.

Unsupported: FASTQ/BAM, SAGE TAG matrices, SOFT family, cross-platform merging, inferred groups, normalization and differential analysis.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
