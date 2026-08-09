# Skills

Each subdirectory is one independently installable, research-first bioinformatics Skill and must contain its own `LICENSE` and a valid `SKILL.md`. The current set contains 20 `preview + reviewed` packages.

Each package owns one recurring job, inspects facts before asking questions, and asks exactly one recommended question at a time only when an unresolved choice would change the result. Optional connectors use two requests: phase 1 discloses provider, purpose, data, credentials, network, cost/rate, and output boundaries and returns a `confirmation_token` without reading configuration; phase 2 may read a local JSON configuration only with both `--acknowledge <exact-confirmation-token>` and `--config <path>`. Missing or mismatched acknowledgement returns `needs-user-confirmation` before any read; after acknowledgement, missing config or credentials returns `needs-user-config` or `needs-credential`. The v0.2.1 repository release bundles connector schema v0.1.0 and a doctor that validates plans only, never a live API call.

`Preview + reviewed` means the exact package passed its declared static and install-smoke gates. It does not imply runtime, scientific-benchmark, human-expert, comparative, or clinical validation. Skipped complex-tool behavior remains unverified.

The authoring baseline lives in `templates/skill/` and is not an installable Skill.
