# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test.

Inputs: One to sixteen LABEL=FastQC reports, plus declared library context.

Outputs: JSON with per-report counts, original filenames, module pass/warn/fail flags and input hashes.

Unsupported: Executing FastQC on raw reads, trimming, mapping, automatic rejection and large MultiQC integrations.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
