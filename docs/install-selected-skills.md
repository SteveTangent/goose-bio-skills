# Install selected Skills

Use the [task bundle and installation guide](task-bundles.md). It covers dependency closure, read-only environment checks, complete-package copying into a new directory, and digest verification.

Install only needed packages from the 56-package catalog. The root is a catalog, not a single Skill. Keep each package’s license, metadata, references, security declaration and script together. Native `agents/openai.yaml` is presentation metadata; `SKILL.md` is the portable entrypoint.

Existing installations are never overwritten or merged by the installer. A new host task may be needed for discovery. Automatic host routing remains unverified; explicitly invoke the installed Skill for a first check.
