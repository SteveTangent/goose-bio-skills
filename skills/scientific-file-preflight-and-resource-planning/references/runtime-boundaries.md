# Runtime and scientific boundaries

This reference defines the operating boundary for
`scientific-file-preflight-and-resource-planning` version `0.4.1`.

## Scientific contract

- Inspect only explicitly named local regular files.
- Keep metadata, suffix hints, magic signatures, and candidate companion files distinct from structural or scientific validation.
- Treat resource values as conservative planning floors under declared operation-class assumptions, not measured runtime predictions.
- Report unsupported, incomplete, or unsafe inspection honestly; identify only
  obvious blockers and heuristic planning floors, not operational readiness.

## Local adapter

The bundled `scripts/preflight_files.py` helper uses Python 3.10+ standard
library interfaces only: `os`, `stat`, `pathlib`, `hashlib`, `json`,
`tempfile`, and `argparse`. It has no network or subprocess dependency.

## Interface freshness

| Component | Reviewed interface | Official documentation | Checked |
| --- | --- | --- | --- |
| Python standard library | Python 3.12.8 runtime; syntax compatible with Python 3.10+ | [Python 3 library reference](https://docs.python.org/3/library/) | 2026-08-09 |

## File and data boundary

An explicit safe local preflight request authorizes metadata reads, a bounded
header probe of at most 1 MiB per named file and 64 MiB total across at most 256
named files, and creation of the requested new report. No duplicate confirmation
is required while the action and scope remain unchanged.

The helper refuses declared symlink leaves, directories, special files, changed
file identities, parent traversal, recursive discovery, decompression, external
commands, existing outputs, and unrequested directory creation. It records a
digest of the bounded probe and whether that probe covered a small file in full;
it never labels the probe as a separately requested whole-file hash. Candidate index
files are checked for presence and regular-file type only; their contents are
not validated.

## Resource assumptions

The helper reports transparent planning floors:

| Operation class | Scratch-space floor | Memory floor | Meaning |
| --- | ---: | ---: | --- |
| `metadata-only` | 1 MiB | 16 MiB | bounded inspection and JSON report only |
| `sequential-read` | 5% of input + 1 MiB | 64 MiB | streaming-style local read; output size remains tool-specific |
| `indexed-analysis` | 125% of input + 1 MiB | 512 MiB | triage floor for an index plus working space; reference/tool costs excluded |
| `sort-or-rewrite` | 300% of input + 1 MiB | 1 GiB | triage floor for rewritten output and temporary runs; tool behavior may exceed it |

Meeting a floor does not prove feasibility. Missing reference data, thread
count, compression behavior, output size, scheduler policy, or tool-specific
memory must remain explicit.

## Verification status

- Mode: `not-performed`
- Self-test: passed with Python 3.12.8; per-file and total caps, signature clues, companion detection, symlink refusal, special-file refusal, and create-exclusive output were checked
- Reason: Agent runtime, large-file calibration, external tools, and scientific benchmarking were not performed
- Unverified boundaries:
  - Resource-planning floors have not been calibrated against large scientific datasets or complex downstream tools
  - Whole-file parsing, decompression, recursive traversal, and external-tool capability probes were not run
  - Windows create-exclusive publication and symlink semantics have not been verified

A helper self-test is not a scientific benchmark. The package remains
`preview + reviewed`.
