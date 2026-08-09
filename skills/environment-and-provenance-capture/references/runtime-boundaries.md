# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`environment-and-provenance-capture`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Capture only caller-authorized files, commands, parameters, versions, timestamps, and digests
- Never dump environment variables, tokens, patient identifiers, full sensitive commands, or private paths
- Read workflow-engine logs and configuration without scheduling or executing the workflow
- Treat provenance completeness as bounded to the declared capture scope

## Optional adapters

- `RO-Crate`
- `W3C PROV-O`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| RO-Crate | 1.3 Recommendation | [RO-Crate Metadata Specification](https://www.researchobject.org/ro-crate/specification/1.3/index.html) | 2026-08-08 |
| W3C PROV-O | W3C Recommendation 2013-04-30 | [PROV-O ontology](https://www.w3.org/TR/prov-o/) | 2026-08-08 |

## Network and data boundary

Core capture is local and read-only. Registry, scheduler, or cloud metadata lookups require explicit network and credential disclosure; this Skill does not submit jobs.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `not-performed`
- Reason: The instruction-only provenance contract was reviewed, but no capture adapter was installed or run; workflow execution is outside scope.
- Relevant versions: RO-Crate 1.3, W3C PROV-O Recommendation
- Unverified boundaries:
  - Live Nextflow, Snakemake, CWL, WDL, Slurm, Modal, container-registry, and cluster integrations have not been run
  - Cloud image-digest and scheduler metadata retrieval has not been evaluated

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
