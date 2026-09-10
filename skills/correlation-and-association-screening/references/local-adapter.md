# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, NumPy, SciPy. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: analyze_correlations.py [-h] [--self-test] [--input INPUT]
                               [--pairs PAIRS] [--output OUTPUT]
                               [--sample-column SAMPLE_COLUMN]
                               [--method {pearson,spearman}]
                               [--inference {none,permutation}]
                               [--missing-policy {error,pairwise}]
                               [--permutations PERMUTATIONS] [--seed SEED]
                               [--independent-units-declared] [--scale SCALE]

Explicit bounded Pearson/Spearman pairs with optional permutation inference.

options:
  -h, --help            show this help message and exit
  --self-test
  --input INPUT
  --pairs PAIRS
  --output OUTPUT
  --sample-column SAMPLE_COLUMN
  --method {pearson,spearman}
  --inference {none,permutation}
  --missing-policy {error,pairwise}
  --permutations PERMUTATIONS
  --seed SEED
  --independent-units-declared
  --scale SCALE
```

Input: Wide numeric TSV with unique sample_id; pairs TSV with x and y; method, inference, scale and missing policy; independent units.

Output: JSON with coefficient, effective n, excluded sample IDs, optional permutation p-values and undefined constant-pair states.

Exclusions: Automatic all-pairs mining, batch adjustment, repeated measures, partial correlation and causal inference.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
