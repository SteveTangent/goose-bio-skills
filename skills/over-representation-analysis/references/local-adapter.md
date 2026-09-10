# Bounded local ORA

The original standard-library helper performs one-sided hypergeometric upper-tail
tests and Benjamini–Hochberg correction over every testable set, including sets
with zero selected overlap. No remote service or downloaded catalog is needed.

```text
python3 scripts/run_ora.py --handoff MAPPED.json --gene-sets SETS.tsv \
  --output NEW_ORA.json --taxon TAXON --namespace NAMESPACE \
  --gene-set-release RELEASE --min-size 10 --max-size 500 --alpha 0.05
```

Alternatively use `--selected SELECTED.tsv --universe UNIVERSE.tsv`, each with
one `gene_id` column. Sets TSV requires exactly `set_id`, `gene_id`, `taxon`,
`namespace`. Declare the actual release; the example sizes/alpha are not universal
defaults. Selected IDs must form a nonempty proper subset of at most 30,000
unique eligible IDs. At most 2,000 testable sets; size bounds 1–10,000; each input
at most 8 MiB. Duplicate rows or mismatched identity are rejected.

Set sizes use the intersection with the universe. Outside members, skipped sets,
overlaps, effect ratios, p-values, adjusted p-values and hashes are recorded.
The caller must establish background eligibility; the helper cannot infer it.

All paths stay inside the chosen working directory, reject symlinks, and must not overwrite an existing output. Run from the data workspace with an absolute path to the installed helper if needed.
