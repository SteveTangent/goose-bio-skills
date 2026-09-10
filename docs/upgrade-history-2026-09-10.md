# Earlier upgrade stages — historical record

These are point-in-time notes retained for traceability. Package counts, pending checks and proposed experiments describe their original stages, not current main. See [current upgrade notes](unreleased-upgrade.md) for the present state. Historical proposals do not create new required work.



## Efficiency and interaction preview — 0.10.0

50 packages, 27 bounded helpers. Added scientific figures and Markdown reporting; implemented local ID mapping, ORA and GSEA, plus count-matrix handoff. Every package has task-aware clarification, terminology and correction guidance. Added selected task bundles, dependency inventory and a create-new installer with digest checks.

Read [task bundles](task-bundles.md), [dialogue examples](user-experience.md) and the [small demo](../examples/efficiency/README.md). These are engineering/content reviewed preview packages; Agent A/B and expert/scientific benchmarks are deferred. No universal superiority claim is made.

Collection VERSION and immutable v0.9.0 release are unchanged. Package artifacts retain independent versions when helper code is unchanged.

---

---

## Initial usability and small-data upgrade

The immutable collection release remains v0.9.0. This working tree keeps 48
packages across 13 domains and 26 clusters. Forty-seven package patches are
0.9.1; count-based differential expression is 0.9.2. All remain
`preview + reviewed`. R6 candidates are outside this upgrade.

| Area | Change | Evidence boundary |
| --- | --- | --- |
| Discovery | 48 descriptions shortened from 17,667 to 8,701 characters; original detailed scope preserved in each body | Metadata size measured; routing improvement not measured |
| Execution guidance | Use existing facts and authorization, respect host hierarchy, load relevant references and finish after applicable checks | Scientific, privacy and file-safety restrictions preserved |
| Native metadata | 48 matching agents/openai.yaml files; no permission overrides | Presentation validated; automatic host discovery not yet exercised |
| Package identity | Separate package patch version from unchanged helper version; full digest still mandatory | Old helpers and expected scientific outputs remain unchanged |
| Replay architecture | Five replay runners share the canonical package-digest function; new v0.2 fixtures bind current packages | Old v0.1 fixtures remain historical evidence, not proof of the new revision |
| Count DE | Original bounded local DESeq2 helper; helper-bearing packages increase from 21 to 22 | Twelve stdlib checks and eight small public-data smoke checks; no scientific generalization claim |
| Installation | Selected-package guide and intact standalone copies checked | Copy integrity and self-tests checked; host routing separate |
| CI | Read-only Linux/macOS package-check matrix | Configuration added; remote runs pending publication |

## Bounded execution added

The count-DE helper accepts an explicitly declared two-level contrast, raw
integer counts and at most one categorical adjustment. It checks sample
alignment, biological-replication declarations, rank, filtering and output
identities. It reports model settings, hashes, versions, warnings and bounded QC.
Existing output files, untrusted paths and unsupported inputs are refused.

The separate smoke run used 14,599 genes and seven public samples (about 0.5 MB
of source tables and metadata); 8,148 genes passed its declared filter. Metadata
permutation left model results unchanged. Incorrect sample identities,
fractional counts, a confounded design, a mismatched tool version and an existing
output were rejected. Dataset-specific transformations are confined to the
research smoke runner, not the installed Skill.

See the [DE adapter](../skills/count-based-differential-expression/references/deseq2-adapter.md),
[selected-install guide](install-selected-skills.md), and
[integration contract](integration-contract.md). Research data and source ledgers
remain outside the package boundary. Dependencies are installed separately;
the helper never downloads data, installs R packages or uploads sample values.

## Verification and remaining limits

Use `python3 scripts/verify.py quick` for package structure, integrity, script
contracts and validator regressions. Use `python3 scripts/verify.py release`
when preparing a release or changing shared replay behavior; it adds connector
and Wave R1–R5 replay checks and compares repeated outputs. These commands do
not perform model-versus-model evaluation or turn preview into stable assurance.

No Astra A/B experiment, representative scientific benchmark, expert review,
remote CI run or clinical validation is claimed. The next useful measurement is
a small real-host comparison on fixed routing and completion tasks, using the
same inputs and settings across no-Skill, previous-Skill and current-Skill runs.
