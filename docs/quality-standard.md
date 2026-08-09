# Skill quality standard

## 1. Capability boundary

A Skill owns one repeatable outcome, not an entire discipline. “Analyze single-cell data” is too broad unless it only routes to narrower Skills. Inputs, outputs, exclusions, near neighbors, and escalation points must be explicit.

## 2. Format and routing

- Follow the current Agent Skills specification.
- Match directory and frontmatter names.
- Make `description` state both the capability and when to use it.
- Keep the activation file lean; move optional domain depth into directly referenced files.
- Include positive, negative, and adversarial routing cases.

## 3. Pre-execution interaction

- Inspect safely discoverable facts before asking the user.
- Ask exactly one atomic question with a recommended answer only when an unresolved user choice would materially change the result; wait before asking another.
- When the current request already authorizes safe local, non-destructive execution and scope is unchanged, proceed without duplicate shared-understanding or execution confirmation.
- Ask one scoped authorization question only for a new material side effect that is not already explicitly authorized for the current action and scope.

## 4. Scientific validity

- Distinguish established practice, benchmark-dependent choice, maintainer guidance, preprint result, and community anecdote.
- Preserve alternatives when assay, organism, reference, data size, experimental design, or compute changes the correct choice.
- State what the Skill cannot infer from the available data.
- Require human inspection for biological interpretation and consequential decisions.

## 5. Freshness

- Record the last check date for tools, packages, APIs, databases, genome references, and file-format assumptions.
- Pin or constrain versions when behavior is version-sensitive.
- Include a migration note when old and new interfaces coexist.
- Mark unverified compatibility as unknown rather than guessing.

## 6. Reproducibility

- Declare environment, inputs, outputs, parameters, randomness, and reference assets that materially affect results.
- Prefer immutable releases and checksums for executable artifacts.
- Use small representative fixtures; never commit sensitive or unnecessarily large biological data.
- Report tool versions and key parameters in generated outputs.

### Bundled-script verification

- Never copy an upstream script verbatim. Evaluate the upstream behavior privately, then create an original reviewed implementation that improves, optimizes, or safely narrows it.
- Give every bundled script one deterministic self-test and record the command and passing status in the manifest; a small deterministic script cannot be marked skipped.
- Record batch-scale, GPU-bound, or complex external-tool runtime testing separately as `skipped-complex-tool` when running it is disproportionate to preview admission, with the reason, relevant tool versions, and every unverified boundary.
- A skip is evidence of a boundary, not evidence that the behavior works. Skipped behavior must not be described as evaluated or included silently in a stable assurance claim.

## 7. Safety and trust

- Treat bundled scripts and third-party commands as executable supply-chain content.
- Minimize permissions and network access.
- Validate inputs at trust boundaries and avoid destructive defaults.
- Never include credentials, protected data, or clinical authority claims.
- Keep the core provider-neutral. External services must remain explicit optional adapters without advertising, sign-up funnels, tracking identifiers, or unsupported vendor rankings. Their tested or unverified state must be visible.

## 8. Evidence and provenance

- Each material recommendation must be traceable in the private research archive to current official guidance or suitable scientific evidence.
- Community reports may identify failure modes but cannot alone establish a recommendation.
- The core Skill must not contain upstream repository credits, source watermarks, or private provenance IDs; publication credits are added later by the project owner.
- Legally required licenses, notices, copyright, and attribution remain mandatory and cannot be hidden by the source-clean policy.

## 9. Evaluation and lifecycle

Lifecycle uses two axes:

- `release_stage`: `preview` or `stable`;
- `assurance_level`: `reviewed` or `evaluated`.

Allowed installable combinations are `preview + reviewed`, `preview + evaluated`, and `stable + evaluated`. `Stable + reviewed` is invalid.

- `reviewed` requires the exact package to pass source, scientific-contract, rights, dependency, safety, sanitization, and static package review. It does not require E5, runtime execution, a scientific benchmark, a no-Skill baseline, or human-expert review; absent human review is recorded as `not-performed`.
- `evaluated` requires bounded evidence for the exact package and must state inputs, versions, method, result, and unverified boundaries. It does not imply universal validity.
- `stable` additionally requires evaluated assurance, a maintained compatibility boundary, no unresolved critical issue in the stable core, and a rollback target.
- A preview package must not claim to be validated, proven better, or better than a baseline. Machine-readable claim fields must match the prose.
- Test the pre-execution state machine statically and, when bounded evaluation is performed, test only the behavior claimed by that evaluation.
- Declare owner, version, both lifecycle axes, review cadence, freshness date, and rollback boundary.
- Re-review after breaking releases, benchmark-changing evidence, or material user failures.
