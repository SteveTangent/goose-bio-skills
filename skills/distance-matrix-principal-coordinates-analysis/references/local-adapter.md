# Local PCoA adapter

Python >=3.10; NumPy is required for execution and its actual version is retained.
The dependency-free self-test checks I/O and distance contracts; numerical small
checks are separate. No external code or data download occurs.

```text
python3 scripts/run_pcoa.py --self-test
python3 scripts/run_pcoa.py --distances distances.tsv --format square-tsv --metric euclidean --metadata groups.tsv --output pcoa-new
python3 scripts/run_pcoa.py --distances beta.json --format beta-json --metric bray_curtis --metadata groups.tsv --output pcoa-new
```

Square TSV: first field sample_id, then unique sample IDs. Rows have the same
IDs in the same order. All entries are finite numeric, exactly symmetric and
nonnegative, with exact zero diagonal. At most 128 characters per sample ID.
Metric is a supplied declaration, not inferred from numbers. Native beta JSON
must use the pairwise-descriptive-beta-diversity-distances schema 1.0; choose
bray_curtis or jaccard_presence_absence. Every pair must be estimated, unique,
and agree with its stored ratio. Missing/zero-depth distances are not imputed.
Optional groups.tsv has exactly sample_id and group with all samples once.

Classical scaling double-centers squared distances: B = -J D² J / 2. A symmetric
eigensolver decomposes B. Positive coordinates are eigenvectors times square
roots of positive eigenvalues; negative coordinates use sqrt(abs(eigenvalue)).
Internal division by the largest distance stabilizes arithmetic; outputs restore
original distance units. Relative eigenvalue tolerance is 1e-10 of the maximum
absolute eigenvalue. Values within tolerance are classified numerical-zero but
remain stored. Axes use lambda / sum(positive lambda above tolerance). Absolute
fractions use abs(lambda) / sum(abs(lambda) above tolerance). Neither silently
uses the signed sum. No Lingoes/Cailliez correction is performed.

Negative inertia fraction is magnitude of negative eigenvalues divided by total
absolute inertia. Inspect it alongside positive-space relative distance error;
there is no automatic universally valid acceptability threshold. Negative axes
are retained in JSON for checking signed squared-distance reconstruction.
Axis signs are oriented by the largest absolute coordinate; tied eigenspaces
can rotate across libraries, so compare reconstructed geometry, not signs.

The visualization Skill consumes pcoa.json with --kind pcoa --result FILE and
--output NEW_DIRECTORY. It carries group labels from the checked native result,
uses equal axis scale and states zero-padding when only one positive axis exists.
The reporting Skill accepts --report ordination=FILE and --figure ordination=DIR.
