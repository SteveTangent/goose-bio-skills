# Matrix to DE handoff

The existing `--count-json` assembly interface remains available. In export mode:

```text
python3 scripts/assemble_gene_count_matrix.py --matrix-json MATRIX.json \
  --metadata SAMPLES.tsv --output NEW_DE_INPUTS
```

Omit `--metadata` to generate a **blank condition template** and a handoff marked
`needs-decision`; never fill biological groups from sample names. With metadata,
require `sample_id`, `condition`, and only an explicitly declared `--covariate`
column, with exact sample matching, two conditions and at least two samples per
condition. These counts do not establish biological independence; clarify it.

The completed assembly must declare 20–30,000 genes and 4–32 unique samples with
nonnegative integer counts. Export creates a new directory with `counts.tsv`,
`samples.tsv` or `samples-template.tsv`, `handoff.json`, and `README.txt`. TSV
outputs are <=8 MiB each. This explicit directory creation is the export-mode
exception to the original single-file assembly boundary; no other paths change.

An export is ready for design checking, not proof that a contrast is estimable.
Pass counts and completed metadata to the count-DE Skill, which checks rank and
requires explicit contrast/filter/model policies.

All paths stay inside the chosen working directory, reject symlinks, and must not overwrite an existing output. Run from the data workspace with an absolute path to the installed helper if needed.
