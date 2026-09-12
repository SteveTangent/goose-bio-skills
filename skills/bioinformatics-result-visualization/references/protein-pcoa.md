# Protein and PCoA delivery

Protein model 0.13.0 uses protein_id and effect_log2; effect direction is the
stored numerator minus denominator on log2 abundance scale. BH correction is
across reported proteins. Never label protein counts as gene counts. The plotting
adapter maps these fields internally and exports protein_id for volcano data;
original result JSON is unchanged. Matrix plots verify the exact input digest.

PCoA 0.13.0 uses native sample/group/coordinate rows. Use --kind pcoa --result
pcoa.json --output NEW_DIRECTORY. Axis percentages use sum of positive
eigenvalues above tolerance; negative inertia and no-correction are stated.
Group colors and point shapes aid comparison but cannot support significance.
A single positive axis explicitly displays the second axis at zero.

Reports accept --report qc=qc.json model=protein.json ordination=pcoa.json and
optional --figure LABEL=DIR. Select only relevant sources for one report. Source
needs-decision remains incomplete even when report file creation succeeds.
Protein QC min/median/max summarize observed values only; missingness mechanism,
normalization suitability and independent subject identity remain declared facts.
