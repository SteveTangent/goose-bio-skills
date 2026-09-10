---
name: environment-and-provenance-capture
description: "Record, compare or verify a biological analysis environment and provenance manifest. Exclude installation, upgrades, pipeline execution and workflow authoring."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Environment and Provenance Capture

`Preview + reviewed`; runtime, scientific, expert, and clinical validation were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: A user needs to record, compare or verify the environment and provenance of a biological computation. Exclude: installing or upgrading software; running a scheduler or workflow engine; uploading manifests without explicit authorization; pipeline design or workflow authoring.

## Owns

Create a portable, read-only provenance record for one planned or completed computational analysis. Apply the detailed scope below.

## Inputs

- commands or workflow steps
- input and output locators
- environment, lockfile or container metadata
- database and reference releases

## Intake

Inspect inputs, tools, versions, and safe metadata first. Ask one unresolved
result-changing question with a recommendation, then wait. Continue approved
safe local work; seek permission for new material side effects.

Decision order:

1. **provenance-boundary.** Which execution boundary must this provenance record cover? Recommended: Cover one declared analysis run with its inputs, commands, parameters, versions, references and outputs.

## Workflow

1. Inspect available environment and workflow facts without changing them.
2. Fingerprint declared inputs and capture tool, runtime and database versions.
3. Record parameters, seeds, references and timestamps with unknowns explicit.
4. Emit a portable manifest and a gap list.
5. Without a compatible declared adapter, return `needs-tool` or `dry-run`; never imply execution.

## Output contract

Return `completed`, `dry-run`, `needs-tool`, or `invalid-input`. `completed` includes:

- versioned provenance manifest
- input and artifact fingerprints
- missing or unverifiable provenance fields

Record fingerprints, parameters, versions, warnings, limitations, and remaining
judgment. Never fabricate a run.

## Runtime and scientific boundaries

Read [runtime-boundaries.md](references/runtime-boundaries.md). Network adapters
disclose provider, purpose, data sent, and credentials; no silent fallback.

## Guardrails

- Capture only caller-authorized files, commands, parameters, versions, timestamps, and digests
- Never dump environment variables, tokens, patient identifiers, full sensitive commands, or private paths
- Write only to a user-approved new output location; never mutate inputs or overwrite a path
- Partial output is never `completed`; use the truthful non-completed status
- Record skipped complex-tool execution as unverified, never as passed
- Keep credentials, private paths, patient and controlled data out of artifacts
- Require researcher review for biological interpretation; no clinical authority
