# Expression sample preparation

For a confirmed independent two-group study, add `--design independent --group-column condition --subject-column subject_id --numerator treated --denominator control`; add `--batch-column batch` only when the original study records it. Declare `--matrix-scale raw-counts` or `log2-normalized` when inspecting a matrix. `continuous` does not establish an expression assay.

The new directory retains the full reordered samples.tsv and validation.json. It also writes plot-groups.tsv and, when supplied, plot-batches.tsv. Only a compatible design yields count-de-samples.tsv and microarray-samples.tsv; select the file matching the assay and model. Metadata preparation never changes or normalizes the expression matrix.

A repeated subject may mean technical replication or paired measurements. Ask which applies, retaining the original sample/subject relationships. `--design paired` reports pair structure but does not authorize the independent expression adapters. Do not silently change subject IDs or discard repeated records to make a model run.

For QC, show the same PCA colored by condition and by batch, and a sample-correlation heatmap on the declared transformed scale. A visually unusual sample is a review item; do not delete it automatically. Technical QC, study provenance and biological plausibility determine the next action.
