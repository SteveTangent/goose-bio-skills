# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: summarize_fastqc.py [-h] [--self-test]
                           [--reports REPORTS [REPORTS ...]] [--output OUTPUT]
                           [--library-context LIBRARY_CONTEXT]

Summarize an explicit small list of existing FastQC reports without reading
raw reads.

options:
  -h, --help            show this help message and exit
  --self-test
  --reports REPORTS [REPORTS ...]
  --output OUTPUT
  --library-context LIBRARY_CONTEXT
```

Input: One to sixteen LABEL=FastQC reports, plus declared library context.

Output: JSON with per-report counts, original filenames, module pass/warn/fail flags and input hashes.

Exclusions: Executing FastQC on raw reads, trimming, mapping, automatic rejection and large MultiQC integrations.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
