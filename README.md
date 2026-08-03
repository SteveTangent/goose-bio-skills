# 02-bio-skills

Curated, installable, evidence-backed bioinformatics agent skills.

本仓库只接收从私有 `skill-research` 流水线导出的、经过优化、评测、脱敏和许可证审查的 Skill。原始仓库映射、私人研究记录和可逆来源指纹不进入本仓库；法律要求的版权、许可证和署名必须保留。

## Status

- Visibility: private
- Maturity: project skeleton
- Published Skills: none yet
- License: intentionally undecided until public-release scope is confirmed

## What belongs here

- one installable directory per Skill under `skills/`
- concise `SKILL.md` instructions following the open Agent Skills format
- only resources required for execution
- public-safe provenance, maintenance metadata, and release notes
- trigger, output, reproducibility, safety, and freshness evidence required by the quality standard

## What does not belong here

- raw external repositories or copied source prose
- private repository URLs, usernames, issue excerpts, or source-to-output maps
- unreviewed scripts, hidden network behavior, credentials, patient data, or controlled datasets
- unsupported claims that a tool is universally best
- Skills that imply clinical diagnosis or validated medical decision-making

## Layout

```text
skills/                 installable Skill packages
templates/skill/        authoring baseline; not an installable Skill
docs/                   catalog, quality, and provenance policy
registry.json           released Skill index
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a Skill.

Quality and release boundaries:

- [Skill quality standard](docs/quality-standard.md)
- [Provenance and sanitization policy](docs/provenance-and-sanitization.md)
- [Candidate capability catalog](docs/catalog.md)
