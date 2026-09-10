# Bounded local ranked enrichment

Use an isolated trusted Python environment with **GSEApy 1.3.0** and pandas.
The helper passes a local gene-set dictionary, disables plots/output directories,
and runs classic weighted gene-set permutation with one thread and a fixed seed.
It never passes a remote collection name or installs tools.

```text
python3 scripts/run_preranked_enrichment.py --handoff MAPPED.json \
  --gene-sets SETS.tsv --output NEW_GSEA.json --taxon TAXON --namespace NAMESPACE \
  --gene-set-release RELEASE --ranking-metric DESeq2-Wald-statistic \
  --positive-direction treated-over-control --min-size 10 --max-size 500 \
  --permutations 1000 --seed 17 --tie-policy gene-id
```

Alternatively `--ranking RANKS.tsv` has exactly `gene_id`, `score`. Sets TSV has
`set_id`, `gene_id`, `taxon`, `namespace`. Require 20–30,000 unique finite scores,
not only significant genes; larger scores mean the declared positive direction.
Reject ties or explicitly choose deterministic gene-ID tie breaking. At most
500 testable sets, 100–10,000 permutations, 8 MiB/input, and
`ranked genes × permutations × testable sets <= 200,000,000`.

Report ES, NES, nominal p-value, **GSEA empirical FDR**, FWER and leading-edge IDs.
Empirical FDR is not a BH-adjusted p-value. Small permutation runs give coarse
estimates; they are appropriate for wiring checks, not precise tail estimates.
No phenotype permutation, multilevel estimation, causal or activation conclusion.

All paths stay inside the chosen working directory, reject symlinks, and must not overwrite an existing output. Run from the data workspace with an absolute path to the installed helper if needed.
