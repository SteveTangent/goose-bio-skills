# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: compare_results.py [-h] [--self-test] [--inputs INPUTS [INPUTS ...]]
                          [--output OUTPUT] [--alpha ALPHA]
                          [--effect-threshold EFFECT_THRESHOLD]
                          [--id-column ID_COLUMN]
                          [--effect-column EFFECT_COLUMN]
                          [--adjusted-p-column ADJUSTED_P_COLUMN]
                          [--tested-column TESTED_COLUMN] [--reverse REVERSE]
                          [--taxon TAXON] [--namespace NAMESPACE]
                          [--positive-direction POSITIVE_DIRECTION]
                          [--effect-scale EFFECT_SCALE]

Compare 2–5 result tables without conflating absent, untested and nonselected
features.

options:
  -h, --help            show this help message and exit
  --self-test
  --inputs INPUTS [INPUTS ...]
  --output OUTPUT
  --alpha ALPHA
  --effect-threshold EFFECT_THRESHOLD
  --id-column ID_COLUMN
  --effect-column EFFECT_COLUMN
  --adjusted-p-column ADJUSTED_P_COLUMN
  --tested-column TESTED_COLUMN
  --reverse REVERSE
  --taxon TAXON
  --namespace NAMESPACE
  --positive-direction POSITIVE_DIRECTION
  --effect-scale EFFECT_SCALE
```

Input: LABEL=TSV tables with feature_id, effect, padj, tested; shared taxon, namespace, effect scale, direction and thresholds.

Output: JSON with explicit not-present/not-tested/tested-not-selected/selected states, direction and common-tested-universe Jaccard.

Exclusions: Meta-analysis, p-value combination, harmonizing incompatible scales or automatic biological ID mapping.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
