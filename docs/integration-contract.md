# Integration contract

Goose Bio Skills keeps the user-facing contract smaller than its package governance.
The files below have different roles and must not be presented as one large
form that a user needs to understand.

## User interaction

- A fully specified request proceeds without a confirmation loop. In the
  retained routing set, 85 of 98 cases require no question.
- When a result-changing fact is genuinely unresolved, ask one recommended
  question and wait. Do not expose the full manifest decision sequence as a
  questionnaire.
- `completed` is reserved for the whole declared job. `partial`, `dry-run`,
  `needs-decision`, `needs-tool`, `invalid-input`, `invalid-output`,
  `provider-failure`, and `io-error` are truthful non-completed outcomes.
- Goose Bio Skills does not yet impose one universal result envelope on scientifically
  different helpers. A host may normalize these outcomes, but package-native
  detail remains authoritative.

## Package metadata

`agents/interface.yaml` is small presentation and compatibility metadata. It
does not grant tools, network access, or filesystem permission. The repository
validator checks its supported fields, but no runtime host integration is
claimed.

`security/permission_policy.json` records the reviewed write boundary for a
bundled helper. `approved` means project review of that declaration; it is not
a host permission grant. The helper's checks and the host's own permission
system remain the enforcement points.

`agents/openai.yaml` contains the matching native Codex presentation subset:
display name, short description and default prompt. It contains no permission,
tool or execution-policy overrides. The validator rejects drift from the
platform-neutral presentation metadata. Host discovery remains a separate check.

A package's version tracks all package bytes. Optional
`script_verification.artifact_version` tracks an unchanged helper's self-test
version independently; when absent, the package version remains the default.
Registry digests still bind the entire package. This allows instruction-only
patches without rewriting old executable fixtures or claiming they evaluated
new agent behavior.

## Networked Skills

Installing one Skill directory installs its instructions, not the repository's
shared connector. Live completion therefore requires either a compatible host
adapter or a separately installed, reviewed Goose Bio Skills connector. Without one, the
Skill must return `needs-tool`, `dry-run`, or `partial` and must not claim a live
call occurred.

This boundary favors portability over bundling a provider client into every
Skill. Provider allowlists, request limits, and anonymous-read rules remain in
the repository connector and package contracts.

## Deliberate non-goals

- no universal scientific workflow API before a real host consumer exists
- no inheritance layer for manifests or interfaces
- no replacement of domain-specific diagnostic fields with generic prose
- no extra user confirmation when safe local work is already authorized

## Optional project handoff companion

The repository-level `scripts/manage_workflow.py` companion stores a small analysis plan and create-new receipts without executing commands. It compares native input hashes, declared parameters and tool versions, package identity, fact evidence, dependency receipts and output files. Scientific fields remain in their original helper outputs. Only fourteen explicitly supported native formats are accepted; installing a standalone Skill does not install this companion.

Reporting may consume checked non-completed results and keeps the source outcome visible. Analysis steps require completed upstream handoffs. `ready` means no handoff gap was detected, not scientific or environment validation. Full usage and current limits: [analysis workflow](analysis-workflow.md).
