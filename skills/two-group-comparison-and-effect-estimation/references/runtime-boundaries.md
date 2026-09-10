# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution.

Inputs: Long TSV: sample_id, group, outcome, value; subject_id for paired data; units, scale, confidence and explicit missing policy.

Outputs: JSON with group sizes, means, mean difference, confidence interval, raw p-value, retained points and exclusions.

Unsupported: Genome-wide count DE, more than two groups, repeated measures beyond pairs, mixed models, covariate adjustment and automatic multiplicity correction.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
