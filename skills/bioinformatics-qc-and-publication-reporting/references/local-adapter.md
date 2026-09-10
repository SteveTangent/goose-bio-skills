# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: build_analysis_report.py [-h] [--self-test]
                                [--reports REPORTS [REPORTS ...]]
                                [--figures [FIGURES ...]] [--note NOTE]
                                [--output OUTPUT] [--title TITLE]
                                [--language {en,zh}]

Assemble a readable Markdown report from explicit local result files and
figure bundles.

options:
  -h, --help            show this help message and exit
  --self-test
  --reports REPORTS [REPORTS ...]
  --figures [FIGURES ...]
  --note NOTE
  --output OUTPUT
  --title TITLE
  --language {en,zh}
```

Input: Labeled result JSON files, optional figure bundles, study context and output language.

Output: New report.md, methods.md, source copies, figures and report.json preserving partial/needs-decision/needs-review states.

Exclusions: Invented results, automatic scientific certification, clinical advice, manuscript conclusions and analysis reruns.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
