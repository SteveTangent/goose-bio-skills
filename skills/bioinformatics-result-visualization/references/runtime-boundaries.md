# Runtime boundaries

The original helper is a small local adapter. It has deterministic standard-library self-tests and separately recorded small execution checks. These checks do not establish agent behavior, scientific benchmark performance, expert approval or superiority to a source repository.

Current versions: Python >=3.10; dependency-free deterministic self-test; NumPy 2.4.4 / SciPy 1.17.1 small local execution; Matplotlib 3.10.8 PNG/SVG rendering smoke.

Inputs: Existing result JSON or explicitly mapped TSV; plot question, scales, significance/direction and display choices.

Outputs: New PNG/SVG, exact plot-data.tsv and figure.json with source hashes, settings and limitations.

Unsupported: Invented values, silent scale conversion, automatic feature fishing, biological conclusions and new statistical tests.

Local write capability is bounded by security/permission_policy.json and host permissions. Missing tools return needs-tool; incomplete decisions remain unresolved. No patient, controlled-access or credential data belongs in distributable artifacts. The core makes no network requests. Optional repository companions remain separate and must disclose their own provider, purpose, data sent and credential boundaries.
