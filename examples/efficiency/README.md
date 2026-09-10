# Small synthetic example

All IDs, gene sets, scores and matrix values in this directory are artificial.
The taxon value is an interface declaration, not a real annotation claim. Results
check software wiring only and have no biological interpretation. Files total
only a few KiB; no download is needed.

Run from this directory. Output names must be new. The following standard-library
steps work without analysis-library installation:

```text
python3 ../../skills/biological-database-record-retrieval-and-identifier-resolution/scripts/resolve_local_ids.py --ids ids.tsv --mapping mapping.tsv --output mapped.json --taxon 9606 --source-namespace demo_source --target-namespace demo_id --mapping-release synthetic-v1 --unresolved-policy preserve
python3 ../../skills/over-representation-analysis/scripts/run_ora.py --selected selected.tsv --universe universe.tsv --gene-sets sets.tsv --output ora.json --taxon 9606 --namespace demo_id --gene-set-release synthetic-v1 --min-size 5 --max-size 20 --alpha 0.05
python3 ../../skills/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py --reports IDs=mapped.json ORA=ora.json --output example-report --language zh --title "Synthetic wiring example"
```

Expected: 40 unique mappings, zero unresolved IDs, three tested sets, and a report
with two completed source steps. `demo_set_0` has overlap 8, universe size 40,
selected size 8, set size 10 and fold enrichment 4. Do not interpret this
artificial selection as a scientific discovery.

With the plotting dependencies available:

```text
python3 ../../skills/bioinformatics-result-visualization/scripts/plot_results.py --kind pca --matrix transformed.tsv --matrix-scale log2-normalized --top-features 10 --feature-scale center --output example-pca
```

With GSEApy 1.3.0 and pandas available:

```text
python3 ../../skills/ranked-gene-set-enrichment/scripts/run_preranked_enrichment.py --ranking ranking.tsv --gene-sets sets.tsv --output gsea.json --taxon 9606 --namespace demo_id --gene-set-release synthetic-v1 --ranking-metric synthetic-score --positive-direction example-positive --min-size 5 --max-size 20 --permutations 100 --seed 17 --tie-policy reject
```

The complete ranked list is used, not only selected.tsv. A 100-permutation run is
an intentionally small wiring check; it does not give precise tail estimates.
Use an absolute path to an installed helper if running from another workspace.
