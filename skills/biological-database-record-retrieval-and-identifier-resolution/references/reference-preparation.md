# Local reference preparation

Use a resource you are authorized to access. Keep its source, resource release and usage terms in your project notes; the helper does not download it, infer its species or bundle a database.

Mapping export:

```text
python3 scripts/resolve_local_ids.py --prepare-reference mapping --reference-input exported.tsv --source-column PROBEID --target-column ENTREZID --source-namespace PLATFORM_PROBE_ID --target-namespace entrez-gene --taxon 9606 --mapping-release DECLARED_RELEASE --output prepared-mapping
```

If a taxon column exists, name it with `--taxon-column`; every row must match. Without that column the species is a declaration about the selected export. Source/target columns must contain one atomic ID per row, not concatenated lists. Empty or missing IDs need an explicit upstream decision. Only exact duplicate pairs are removed and counted; multi-valued relationships remain rows.

For GMT, use `--prepare-reference gene-sets --reference-input sets.gmt --target-namespace entrez-gene --taxon 9606 --mapping-release DECLARED_COLLECTION_RELEASE --output prepared-sets`. Each line contains set ID, description and member IDs. Repeated set names are rejected; repeated members are deduplicated and counted. The description is omitted without following its contents or links. Output is gene-sets.tsv plus resource.json. Use the recorded collection release as --gene-set-release downstream.

Mapping tables and gene-set files are not interchangeable. Review the mapping summary: unique, unmapped, ambiguous and many-to-one fractions. `preserve` leaves unresolved mappings partial; explicit `exclude` removes them from both eligible background and selected/ranked lists. It never chooses the first match or merges probes based on significance. This can remove many microarray probes; consider a documented pre-fit summarization policy if the scientific question needs gene-level estimates.
