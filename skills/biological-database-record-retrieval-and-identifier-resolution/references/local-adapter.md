# Bounded local mapping

Run `python3 scripts/resolve_local_ids.py --help` for the complete interface.
Choose exactly one input: `--ids` (TSV with one `gene_id` column) or
`--de-report` (completed Goose DESeq2 or microarray limma JSON). Supply `--mapping` TSV with exactly
`source_id`, `target_id`, `taxon`; `--taxon`, `--source-namespace`,
`--target-namespace`, `--mapping-release`, `--unresolved-policy preserve|exclude`,
and a new `--output` JSON. DE input additionally requires `--alpha` and
`--effect-threshold` (absolute log2 fold change).

Every file is at most 8 MiB, at most 30,000 input IDs. All mapping rows must have
the declared taxon. No network lookup or user-list submission occurs. One-to-many,
unmapped and many-to-one collisions remain visible. `preserve` returns partial
when unresolved; `exclude` requires that explicit policy and records losses.
Never choose the first match or silently merge duplicated targets.

`--strip-source-version` is an explicit Ensembl gene-ID policy only. Namespace
and organism are declarations, not inferred from a successful string match.

A completed DE handoff contains separate `selected`, `universe` and `ranking`
records. ORA eligibility requires finite selection statistics; ranked enrichment
retains every finite signed test statistic even when adjusted p-values are unavailable.
Use the handoff directly with local ORA/GSEA, preserving the target namespace.

All paths stay inside the chosen working directory, reject symlinks, and must not overwrite an existing output. Run from the data workspace with an absolute path to the installed helper if needed.
