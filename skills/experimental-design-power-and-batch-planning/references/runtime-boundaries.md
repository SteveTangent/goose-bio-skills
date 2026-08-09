# Runtime and scientific boundaries

This reference defines the source-clean operating boundary for
`experimental-design-power-and-batch-planning`. It records interfaces reviewed on 2026-08-08; it does not claim
that the tools were installed or runtime-tested in this preview.

## Scientific contract

- Declare estimand, outcome model, independent unit, meaningful effect, variance source, alpha, power or precision target, dropout, allocation, and budget
- Check design-matrix rank and prevent treatment, batch, site, or processing order from becoming confounded
- Use statsmodels only for supported analytic models; do not present it as a universal omics power engine
- Report power and precision as conditional on assumptions, never as a guarantee

## Optional adapters

- `statsmodels`

These names identify compatible capability surfaces, not rankings or silent
dependencies. Record the exact local version and command before execution.

## Interface freshness

| Component | Reviewed version/interface | Official documentation | Checked |
| --- | --- | --- | --- |
| statsmodels | 0.14.6 | [analytic power and sample-size functions](https://www.statsmodels.org/stable/stats.html) | 2026-08-08 |

## Network and data boundary

The core design contract is offline and database-free. Sensitive budgets, effects, and schedules remain local; external optimization or simulation services require separate authorization.

Before any network call, disclose the provider, query or data fields sent,
credential requirement, rate or access constraint, and local output location.
Never upload controlled or patient data under this preview contract.

## Verification status

- Mode: `skipped-complex-tool`
- Reason: Assay-specific simulation, large Monte Carlo studies, integer optimization, and hierarchical-design software were not executed.
- Relevant versions: statsmodels 0.14.6 reviewed; not executed, assay-specific simulation engine not-selected
- Unverified boundaries:
  - Assay-specific count, single-cell, spatial, hierarchical, and multi-stage power models have not been evaluated
  - Large Monte Carlo simulation, allocation optimization, and cluster or batch random-effects behavior have not been run

A skip is not a pass. The exact package remains `preview + reviewed` until a
separate bounded evaluation records what actually ran.
