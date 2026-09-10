# Bounded local adapter

Run from a working directory containing the input files and an existing parent for the requested new output. Paths stay within that directory. No overwrite or hidden network. Install trusted dependencies separately; this helper does not install anything.

Adapters: Python standard library. Tested versions are recorded in manifest.json. Small h5ad execution additionally needs Python compatible with the declared AnnData/Scanpy versions; the generic Python minimum only describes standard-library checks.

```text
usage: prepare_geo_matrix.py [-h] [--self-test] [--accession ACCESSION]
                             [--index INDEX] [--matrix MATRIX]
                             [--platform PLATFORM] [--output OUTPUT]
                             [--samples SAMPLES]
                             [--scale {raw-counts,tpm,log2-normalized,processed-other,unknown}]

Plan a bounded GEO matrix retrieval or prepare one explicitly selected local
Series Matrix.

options:
  -h, --help            show this help message and exit
  --self-test
  --accession ACCESSION
  --index INDEX
  --matrix MATRIX
  --platform PLATFORM
  --output OUTPUT
  --samples SAMPLES
  --scale {raw-counts,tpm,log2-normalized,processed-other,unknown}
```

Input: One GSE; bounded downloaded Series Matrix with ID_REF; selected GPL; declared scale (unknown allowed); optional curated sample_id/condition table.

Output: New expression.tsv, features.tsv, samples.tsv, original-samples.tsv and preparation.json; unresolved scale/groups remain needs-decision.

Exclusions: FASTQ/BAM, SAGE TAG matrices, SOFT family, cross-platform merging, inferred groups, normalization and differential analysis.

Files are bounded to 8 MiB per local input. Tabular jobs apply additional row/work limits.

## Optional shared GEO retrieval

The installed core works on local files. Repository users may run the shared `scripts/run_research_connector.py` companion with provider `ncbi-geo-files` to retrieve the exact directory URL returned by this helper, then one selected matrix filename. This companion is outside the standalone package and may be unavailable after package-only installation; then ask the user for the downloaded matrix or use a reviewed host read adapter. Do not silently download through an arbitrary URL.

Only a public GSE accession and selected filename are sent to NCBI. No credentials, sample uploads or paid use. The host's proxy/trust policy still applies. Directory links are untrusted data; accept only matching Series Matrix filenames. Download cap is 5 MiB, expanded matrix cap is 16 MiB, one platform and at most 30,000 features/256 samples. Inspect scale and grouping before downstream analysis. Unknown scale cannot authorize count DE.
