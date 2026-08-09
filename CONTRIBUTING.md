# Contributing

The repository is private during the research phase. Contributions should start as evidence-backed proposals rather than copied Skill folders.

## Propose a Skill

Provide:

- the recurring job it should own
- realistic inputs and the finished output contract
- should-trigger, should-not-trigger, and near-neighbor examples
- biological and computational assumptions
- current official references and relevant benchmark evidence
- known failure modes, safety limits, and required human review
- a minimal representative fixture or reproducible example

Source identities and raw comparison notes belong in the private research archive.

The installable core must not contain upstream repository credits, source watermarks, or private provenance IDs. The project owner will add an approved source list or unified credit treatment later in the publication cover/release layer.

## Promotion checklist

- [ ] Capability boundary is narrower than a whole scientific field.
- [ ] Source license and attribution obligations were reviewed.
- [ ] Instructions were synthesized, not stitched from source prose.
- [ ] Tool/API/package freshness was checked and dated.
- [ ] Trigger and output boundaries were reviewed; any actual evaluation is declared separately and bound to the exact package.
- [ ] Near-neighbor routing remains clean.
- [ ] Discoverable facts are checked before asking, and only unresolved load-bearing choices are asked one at a time with a recommendation.
- [ ] An explicitly requested safe local action does not receive a duplicate confirmation; a new material side effect is confirmed only if the same action and scope were not already authorized.
- [ ] Scientific limitations and human review points are explicit.
- [ ] The core is provider-neutral and optional adapters contain no advertising, sign-up funnel, tracking, or forced vendor ranking.
- [ ] No secret, private path, protected data, or unnecessary source identity is present.
- [ ] No upstream source credit, source watermark, or private provenance ID is embedded in the core Skill.
- [ ] No third-party watermark was removed from a reused asset.
- [ ] No upstream script was copied verbatim; each bundled script is an original reviewed rewrite.
- [ ] Every bundled script passed a deterministic self-test; any separate batch/GPU/complex-tool runtime skip records its reason, versions, and unverified boundaries.
- [ ] Legally required `LICENSE`, `NOTICE`, copyright, and attribution remain intact.
- [ ] Owner, version, `release_stage`, `assurance_level`, freshness date, and review cadence are declared.
- [ ] A preview package makes no validated, proven-better, or better-than-baseline claim.

## Public release

Do not make this repository public until a project license is chosen, every included dependency and derived artifact is license-compatible, and the provenance/sanitization audit passes.

Run `python3 scripts/validate_skeleton.py` before review. It checks the intake contract, atomic package/registry boundary, local-path leakage, and common GitHub secret patterns.
