---
name: human-variant-evidence-retrieval
description: "Retrieve bounded ClinVar evidence for one to five exact Variation IDs or VCV accessions. Exclude allele search, RCV lookup, pathogenicity reassessment and clinical decisions."
license: Apache-2.0
metadata:
  version: "0.10.0"
---

# Human Variant Evidence Retrieval

`Preview + reviewed`; the deterministic normalizer self-test and one bounded
public record retrieved through both exact identifier forms passed as developer
canaries. Formal agent runtime, representative-data benchmarking, scientific
evaluation, and expert review were not performed.

## Execution behavior

Use supplied and safely inspected facts first. Explain an unfamiliar term only
when it changes the decision. If a critical fact is missing or inconsistent,
follow [the dialogue guide](references/user-dialogue.md): ask one focused
question, explain why, recommend a defensible route, and wait on dependent work.
Continue independent authorized work; never guess scientific facts or repeat a
resolved question. With complete inputs, proceed. Show relevant figures/tables
and their meaning; preserve the host's permissions and the boundaries below.
Finish with outputs, key findings and concrete remaining limits.


Detailed scope: Use for bounded retrieval and provenance-bound normalization of public ClinVar evidence for one to five exact numeric Variation IDs or VCV accessions. Preserve VCV and SCV identities, provider classifications, review status, conditions, dates, submitters, aggregate records, missing results, and conflicts without resolving them. Exclude free-text variant search or resolution, Allele IDs, RCV- or SCV-led retrieval, VCF processing, variant calling, ACMG classification, evidence scoring, diagnosis, treatment, and clinical recommendations.

## Owns

Retrieve public ClinVar VCV XML for one to five exact identifiers and normalize
provider assertions without changing, ranking, scoring, or reconciling them.

## Inputs and intake

Require exact identifiers and a new JSON output path. Accept only positive
numeric ClinVar Variation IDs or uppercase VCV accessions with nine digits and
an optional version. A bare integer must be explicitly identified as a
Variation ID, because ClinVar Allele IDs use an overlapping number space.
Request each Variation ID only once per run, not through equivalent identifier
forms or multiple versions.

Inspect safe facts first. Ask one unresolved question with a recommendation,
then wait:

1. **numeric-identifier-namespace.** Does each bare integer mean a ClinVar
   Variation ID? Recommended: require the issuer-recorded `Variation ID` label;
   do not guess from the number.

An explicit request authorizes the bounded anonymous public reads and one
create-new local report.

## Retrieve

Use the repository shared connector with provider `ncbi-eutils`, one EFetch VCV
request per identifier, at most five requests. For a numeric ID use the official
`is_variationid=true` form; for VCV use the exact accession and preserve a
requested version. Save each XML payload with its connector-generated
`.provenance.json` sidecar. Do not search, resolve names, or fall back to another
provider. Read [runtime boundaries](references/runtime-boundaries.md) before the
first live call.

If the reviewed connector or network is unavailable, return `needs-tool` with
the exact dry-run request plan. Never claim retrieval or fabricate provenance.

## Normalize

Repeat `--identifier` and `--input` in the same order for multiple records:

```text
python3 scripts/normalize_clinvar_vcv.py \
  --identifier VCV000009325 --input VCV000009325.xml \
  --output NEW_CLINVAR_EVIDENCE.json
```

The dependency-free Python 3.10+ helper accepts regular XML payloads and their
automatic provenance sidecars. It checks the connector schema, declared
provider, exact endpoint and identifier, response metadata, filename, byte
count, and SHA-256 binding before normalization. Inputs may use explicit
relative or absolute paths; leaf symlinks and existing outputs are refused.
All input opens are nonblocking and are accepted only after descriptor-level
regular-file checks, so FIFOs and other special files are rejected without a
read. Only UTF-8 XML is accepted, DTD/entity declarations are rejected, and an
explicit ClinVar error or warning envelope returns `provider-failure` rather
than a missing-record result. Output paths are confined to the current working
directory; parent traversal and symlinked parent components are refused.

The sidecar is unsigned: these checks detect mismatches but do not
cryptographically authenticate its origin. Use only a sidecar retained directly
from the reviewed connector; never hand-author one.

## Output contract

Return `completed`, `partial`, `needs-tool`, `provider-failure`, `invalid-input`,
`invalid-output`, or `io-error`. Publication is temporary-first and create-new; a failed
publication rolls back any output link it created. A created JSON report preserves:

- requested, returned, and missing identifiers plus VCV versions and record dates;
- aggregate classification subtrees, review status, RCV accessions, and counts;
- each ClinicalAssertion and SCV, submitter, classification, review status,
  condition subtree, dates, and aggregate-contribution flag;
- payload and provenance fingerprints, retrieval time, provider, endpoint
  class, and response status.

Label conflict resolution and clinical interpretation `not-performed`.

## Guardrails

- Never convert a bare integer into a Variation ID without the declared namespace.
- Never collapse conditions, submitters, classifications, versions, or conflicts.
- Never run free-text resolution, ACMG classification, scoring, diagnosis,
  treatment, causal inference, or clinical recommendations.
- Keep patient, private, unpublished, and controlled data out of public services.
- Normal execution never overwrites, mutates inputs, creates directories, uses
  credentials, accesses the network, or starts subprocesses. `--self-test`
  creates and cleans only its owned system-temporary fixture directory.
- Require researcher review; this preview has no clinical or diagnostic authority.
