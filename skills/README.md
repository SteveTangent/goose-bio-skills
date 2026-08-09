# Skills

Each subdirectory is one independently installable, research-first bioinformatics Skill and must contain its own `LICENSE` and a valid `SKILL.md`. The current set contains 20 `preview + reviewed` packages.

Each package owns one recurring job, inspects facts before asking questions, and asks exactly one recommended question at a time only when an unresolved choice would change the result. In v0.3.0, an explicit request authorizes the matching bounded read and requested download from a declared public provider. The shared companion is anonymous-only; paid and metered providers are absent. Sensitive uploads, remote jobs, unrequested bulk expansion, and terms-restricted access require an exact scoped confirmation. Conditional jobs require a reviewed host adapter or return `needs-tool`; an authenticated adapter is a separate disclosed boundary. A package may claim `completed` only for checked live responses with provenance; incomplete, blocked, and failed work remains explicit.

`Preview + reviewed` means the exact package passed its declared static and install-smoke gates. It does not imply runtime, scientific-benchmark, human-expert, comparative, or clinical validation. Skipped complex-tool behavior remains unverified.

The authoring baseline lives in `templates/skill/` and is not an installable Skill.
