# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: Labeled result JSON files, optional figure bundles, study context and output language.

Outputs: New report.md, methods.md, source copies, figures and report.json preserving partial/needs-decision/needs-review states.

Unsupported: Invented results, automatic scientific certification, clinical advice, manuscript conclusions and analysis reruns.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
