# qPCR and independent categorical result delivery

Only completed native 0.14.0 results produce analysis figures. A needs-decision
source remains incomplete in the report even if report creation itself completes.

qPCR: use --kind qpcr --result qpcr.json --outcome TARGET --output NEW_DIRECTORY.
Choose one target explicitly when several are available. One point represents an
independent subject, technical wells are averaged upstream, and the horizontal
line is the mean log2 relative expression. This is relative to the declared
calibrator group. Do not label points as technical wells or compare different
assays as absolute abundance. No group test, uncertainty interval or significance
stars are added. Linear and log2 values must agree before plotting.

Categorical: use --kind categorical --result comparison.json --output NEW_DIRECTORY.
The plot shows observed integer counts, group totals, conditional OR and its exact
interval, and Fisher's p-value. Infinity and zero are displayed explicitly. It is
not a risk plot. Event and comparison direction remain the original labels;
case-control sampling does not identify population risks from observed fractions.

The report accepts --report LABEL=FILE and optional --figure LABEL=DIRECTORY.
Use --language zh for Chinese explanations of biological n, calibration and odds
ratio meaning. The p-value and interval use distinct two-sided conventions;
report both without automatically asserting they must agree at one threshold.
