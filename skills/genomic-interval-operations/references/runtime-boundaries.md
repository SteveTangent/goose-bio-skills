# Runtime boundaries

The original standard-library 0.15.0 adapter executes only bounded exact BED3
merge and intersection. Local format and method semantics checked 2026-09-13;
small original execution records remain separate from Agent/scientific evaluation.
Read [the local contract](local-adapter.md) for exact limits and outputs.

Broader guidance may use a locally declared bedtools, Gtars or polars-bio adapter.
Record its installed version, operation, coordinate/strand policies and input
fingerprints before execution. No tool is installed automatically, and the new
helper does not claim cross-engine equivalence. Without a compatible tool,
return needs-tool or a clearly labeled plan for subtraction/nearest/strand tasks.

Whole-genome joins, distributed/cloud tables, remote reference retrieval,
performance scaling, lift-over and scientific interpretation remain unverified.
Same build labels are supplied facts, not assembly identity proven from coordinates.
Remote inputs require separately authorized retrieval and provider provenance;
the core helper remains local and offline. No patient or controlled-data upload.
