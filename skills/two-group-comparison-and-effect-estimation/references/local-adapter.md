# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library, NumPy, SciPy. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: compare_groups.py [-h] [--self-test] [--input INPUT] [--output OUTPUT]
                         [--numerator NUMERATOR] [--denominator DENOMINATOR]
                         [--unit UNIT] [--sample-column SAMPLE_COLUMN]
                         [--group-column GROUP_COLUMN]
                         [--outcome-column OUTCOME_COLUMN]
                         [--value-column VALUE_COLUMN]
                         [--subject-column SUBJECT_COLUMN]
                         [--method {welch,paired}]
                         [--missing-policy {error,complete}]
                         [--scale {continuous,log2-normalized}]
                         [--confidence CONFIDENCE]
                         [--independent-units-declared]

One declared independent or paired two-group continuous-outcome comparison.

options:
  -h, --help            show this help message and exit
  --self-test
  --input INPUT
  --output OUTPUT
  --numerator NUMERATOR
  --denominator DENOMINATOR
  --unit UNIT
  --sample-column SAMPLE_COLUMN
  --group-column GROUP_COLUMN
  --outcome-column OUTCOME_COLUMN
  --value-column VALUE_COLUMN
  --subject-column SUBJECT_COLUMN
  --method {welch,paired}
  --missing-policy {error,complete}
  --scale {continuous,log2-normalized}
  --confidence CONFIDENCE
  --independent-units-declared
```

Input: Long TSV: sample_id, group, outcome, value; subject_id for paired data; units, scale, confidence and explicit missing policy.

Output: JSON with group sizes, means, mean difference, confidence interval, raw p-value, retained points and exclusions.

Exclusions: Genome-wide count DE, more than two groups, repeated measures beyond pairs, mixed models, covariate adjustment and automatic multiplicity correction.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.
