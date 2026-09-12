# Runtime boundary

This original offline helper launches only a fixed embedded R worker with `--vanilla`, a declared trusted Rscript and bounded data files. User fields are TSV values, not executable expressions. Python standard-library checks do not install scientific dependencies. R 4.4.1 and limma 3.60.6 are explicitly checked; other environments return needs-tool.

Use a trusted local workspace. Local no-overwrite checks do not establish protection against a hostile concurrent writer or replacement R installation. No network, credentials, uploads, paid services or clinical use. Leave missing facts unresolved and retain warnings. A successful fit does not establish study adequacy, causal mechanisms, generalization or human expert review.
