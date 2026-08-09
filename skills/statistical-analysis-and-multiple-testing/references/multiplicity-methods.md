# Multiplicity method boundaries

Use these references to check method semantics, not to infer a user's multiplicity family.

- Holm S. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*. 1979;6:65–70. DOI: `10.2307/4615733`.
- Benjamini Y, Hochberg Y. Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*. 1995;57(1):289–300. DOI: `10.1111/j.2517-6161.1995.tb02031.x`.
- R Core Team. `stats::p.adjust` documentation: https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html (checked 2026-08-08).

Operational boundary:

- Holm controls FWER under arbitrary dependence when each null-hypothesis p-value is valid and therefore conservatively controls FDR because FDR is no greater than FWER. Holm is FWER-targeting, not FDR-targeting.
- Ordinary BH is FDR-targeting, but its standard guarantee requires independence or appropriate positive dependence. If a user explicitly requires an FDR-targeting procedure under unknown or arbitrary dependence and disallows FWER substitution, neither bundled method matches; do not silently substitute Holm or claim ordinary BH provides that guarantee.
- Adjust within the declared family. If family membership or the error-control objective is unresolved, stop before adjustment.
- Stable ordering is only a deterministic tie policy; it does not change the mathematical family or method.
