# Skill quality standard

## 1. Capability boundary

A Skill owns one repeatable outcome, not an entire discipline. “Analyze single-cell data” is too broad unless it only routes to narrower Skills. Inputs, outputs, exclusions, near neighbors, and escalation points must be explicit.

## 2. Format and routing

- Follow the current Agent Skills specification.
- Match directory and frontmatter names.
- Make `description` state both the capability and when to use it.
- Keep the activation file lean; move optional domain depth into directly referenced files.
- Include positive, negative, and adversarial routing cases.

## 3. Scientific validity

- Distinguish established practice, benchmark-dependent choice, maintainer guidance, preprint result, and community anecdote.
- Preserve alternatives when assay, organism, reference, data size, experimental design, or compute changes the correct choice.
- State what the Skill cannot infer from the available data.
- Require human inspection for biological interpretation and consequential decisions.

## 4. Freshness

- Record the last check date for tools, packages, APIs, databases, genome references, and file-format assumptions.
- Pin or constrain versions when behavior is version-sensitive.
- Include a migration note when old and new interfaces coexist.
- Mark unverified compatibility as unknown rather than guessing.

## 5. Reproducibility

- Declare environment, inputs, outputs, parameters, randomness, and reference assets that materially affect results.
- Prefer immutable releases and checksums for executable artifacts.
- Use small representative fixtures; never commit sensitive or unnecessarily large biological data.
- Report tool versions and key parameters in generated outputs.

## 6. Safety and trust

- Treat bundled scripts and third-party commands as executable supply-chain content.
- Minimize permissions and network access.
- Validate inputs at trust boundaries and avoid destructive defaults.
- Never include credentials, protected data, or clinical authority claims.

## 7. Evidence and provenance

- Each material recommendation must be traceable to current official guidance or suitable scientific evidence.
- Community reports may identify failure modes but cannot alone establish a recommendation.
- Public provenance must satisfy licenses without exposing the private source map.

## 8. Evaluation and lifecycle

- Compare with a no-Skill baseline.
- Require deterministic assertions for material output properties and human review for judgment-heavy quality.
- Declare owner, version, status, review cadence, and deprecation path.
- Re-review after breaking releases, benchmark-changing evidence, or material user failures.
