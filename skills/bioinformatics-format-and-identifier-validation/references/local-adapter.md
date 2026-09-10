# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: validate_sample_table.py [-h] [--self-test] [--metadata METADATA]
                                [--matrix MATRIX] [--output OUTPUT]
                                [--sample-column SAMPLE_COLUMN]
                                [--group-column GROUP_COLUMN]
                                [--subject-column SUBJECT_COLUMN]
                                [--batch-column BATCH_COLUMN]
                                [--rename RENAME]
                                [--matrix-scale {raw-counts,continuous,unknown}]

Validate an explicit sample table, optionally align it to a bounded matrix.

options:
  -h, --help            show this help message and exit
  --self-test
  --metadata METADATA
  --matrix MATRIX
  --output OUTPUT
  --sample-column SAMPLE_COLUMN
  --group-column GROUP_COLUMN
  --subject-column SUBJECT_COLUMN
  --batch-column BATCH_COLUMN
  --rename RENAME
  --matrix-scale {raw-counts,continuous,unknown}
```

Input: Sample TSV; optional matrix; declared sample/group/subject/batch columns, matrix scale and explicit renames.

Output: New samples.tsv and validation.json with input hashes, renames, sample order, unresolved fields and design warnings.

Exclusions: Inferred groups, silent sample drops, automatic ID mapping, data imputation or choosing a statistical model.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
