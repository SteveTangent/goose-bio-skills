# Current source-code graph

The local CodeGraph index was refreshed on 2026-09-10 after the native
metadata, small-analysis adapters, GEO connector and shared replay-digest changes. Its generated
database is ignored and must be rebuilt from source in each checkout; use
`codegraph status` for current counts rather than treating a historical count
as a release gate.

Use the graph for implementation impact, callers, callees, and automation
structure. It does not parse the scientific meaning of `SKILL.md`, prove route
quality, or add evaluated assurance. Package dependencies, lifecycle state,
and exact package identity remain authoritative in manifests, the registry,
and release evidence.

The contributor pipeline is shown in
[`verification-pipeline.md`](verification-pipeline.md). The research evidence
graph and private source provenance remain in `skill-research`; they are not
copied into this source-clean package repository.
