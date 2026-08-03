# 02-bio-skills

Curated, installable, evidence-backed bioinformatics agent skills.

本仓库只接收从私有 `skill-research` 流水线导出的、经过优化、评测、脱敏和许可证审查的 Skill。原始仓库映射、私人研究记录、来源说明、来源水印和溯源 ID 均不进入核心 Skill。项目所有者以后会在发布封面或发行页面统一添加来源，避免不同来源标记与水印互相干扰。法律强制要求的版权、`LICENSE`、`NOTICE` 或署名是唯一默认例外。

## Status

- Visibility: private
- Maturity: project skeleton
- Published Skills: none yet
- License: intentionally undecided until public-release scope is confirmed

## What belongs here

- one installable directory per Skill under `skills/`
- concise `SKILL.md` instructions following the open Agent Skills format
- only resources required for execution
- maintenance metadata and release notes without upstream source presentation
- trigger, output, reproducibility, safety, and freshness evidence required by the quality standard

## What does not belong here

- raw external repositories or copied source prose
- private repository URLs, usernames, issue excerpts, or source-to-output maps
- upstream source credits, source watermarks, or private provenance IDs inside the core Skill
- third-party assets whose watermarks would need to be removed
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

Source credits belong to a later owner-controlled publication layer, not to the installable core package.

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a Skill.

Quality and release boundaries:

- [Skill quality standard](docs/quality-standard.md)
- [Source separation and sanitization policy](docs/provenance-and-sanitization.md)
- [Candidate capability catalog](docs/catalog.md)
