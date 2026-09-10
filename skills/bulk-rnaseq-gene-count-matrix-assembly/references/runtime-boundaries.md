# Runtime boundaries

- Agent routing and interactive behavior have not been runtime-evaluated.
- Scientific benchmark performance and human-expert review have not been established.
- Basic helper execution uses small fixtures only; dataset generalization and large jobs are unverified.
- The helper verifies exact report-level GTF, gene-row, and assignment-contract agreement but cannot independently verify the underlying SAM, GTF, sample identity, protocol, or cohort suitability.
- The full upstream reference dictionary is not present in the source-report schema, so equality is bounded to the GTF SHA-256 and gene tuples exposed by those reports.
- Create-new publication has tested rollback after staged identity is recorded; a rare pre-identity failure may leave a hidden mode-0600 stage, it is not crash-atomic, and malicious same-directory writers were not evaluated.
- Windows create-new publication and symlink semantics have not been verified.

The bundled local adapter is documented in [local-adapter.md](local-adapter.md). Other adapters retain their explicit limits; no silent fallback or network submission is permitted.
