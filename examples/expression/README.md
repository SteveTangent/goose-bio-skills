# 小型表达分析示例

四个文件是原创合成数据：200 个探针、8 个独立样本、两个组和均衡的两个批次；映射与三个基因集也都是合成设置。它们不能用于证明生物学结论。文件共约 20 KiB。先将这个目录复制到新的分析目录，安装对应任务包及已声明依赖，再从该目录执行。以下以 `SKILLS` 表示实际安装目录，不是固定系统路径。

```bash
python3 "$SKILLS/bioinformatics-format-and-identifier-validation/scripts/validate_sample_table.py" --metadata samples.tsv --matrix expression.tsv --matrix-scale log2-normalized --design independent --group-column condition --subject-column subject_id --batch-column batch --numerator treated --denominator control --output validation
python3 "$SKILLS/normalized-microarray-differential-expression/scripts/run_microarray_de.py" --expression expression.tsv --metadata validation/microarray-samples.tsv --output fit --assay microarray --scale log2-normalized --feature-unit probe --taxon 9606 --namespace synthetic-probe --platform synthetic-platform --normalization-provenance "Original simulated log2 expression; no measured study claim" --numerator treated --denominator control --covariate batch --alpha .05 --independent-samples-declared
python3 "$SKILLS/biological-database-record-retrieval-and-identifier-resolution/scripts/resolve_local_ids.py" --prepare-reference mapping --reference-input reference.tsv --source-column probe --target-column gene --taxon-column species --source-namespace synthetic-probe --target-namespace synthetic-gene --taxon 9606 --mapping-release synthetic-1 --output mapping-resource
python3 "$SKILLS/biological-database-record-retrieval-and-identifier-resolution/scripts/resolve_local_ids.py" --prepare-reference gene-sets --reference-input sets.gmt --target-namespace synthetic-gene --taxon 9606 --mapping-release synthetic-1 --output set-resource
python3 "$SKILLS/biological-database-record-retrieval-and-identifier-resolution/scripts/resolve_local_ids.py" --de-report fit/de.json --mapping mapping-resource/mapping.tsv --taxon 9606 --source-namespace synthetic-probe --target-namespace synthetic-gene --mapping-release synthetic-1 --unresolved-policy preserve --alpha .05 --effect-threshold 1 --output mapped.json
python3 "$SKILLS/over-representation-analysis/scripts/run_ora.py" --handoff mapped.json --gene-sets set-resource/gene-sets.tsv --taxon 9606 --namespace synthetic-gene --gene-set-release synthetic-1 --min-size 5 --max-size 100 --alpha .05 --output ora.json
python3 "$SKILLS/ranked-gene-set-enrichment/scripts/run_preranked_enrichment.py" --handoff mapped.json --gene-sets set-resource/gene-sets.tsv --taxon 9606 --namespace synthetic-gene --gene-set-release synthetic-1 --ranking-metric "moderated t" --positive-direction treated --min-size 5 --max-size 100 --permutations 100 --seed 127 --tie-policy gene-id --output gsea.json
python3 "$SKILLS/bioinformatics-result-visualization/scripts/plot_results.py" --kind volcano --de-report fit/de.json --significance padj --alpha .05 --effect-threshold 1 --output volcano
python3 "$SKILLS/bioinformatics-result-visualization/scripts/plot_results.py" --kind pca --de-report fit/de.json --matrix expression.tsv --matrix-scale log2-normalized --metadata validation/plot-groups.tsv --top-features 100 --feature-scale center --output pca
python3 "$SKILLS/bioinformatics-result-visualization/scripts/plot_results.py" --kind sample-correlation --de-report fit/de.json --matrix expression.tsv --matrix-scale log2-normalized --metadata validation/plot-groups.tsv --top-features 100 --feature-scale center --output sample-correlation
python3 "$SKILLS/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py" --title "合成表达数据检查" --language zh --report validation=validation/validation.json de=fit/de.json mapping=mapped.json ora=ora.json gsea=gsea.json --figure volcano=volcano pca=pca sample-correlation=sample-correlation --output report
```

查看 report/report.md、methods.md 和原生结果 JSON。重复运行时使用新的输出目录，避免覆盖先前结果。若需要持久化事实和恢复步骤，由 Agent 结合 [微阵列模板](../workflow/microarray-expression.json) 维护分析计划并逐步登记结果；上述计算脚本本身不修改计划。

替换成自己的数据时，重新核对物种、平台、尺度、归一化来源、分组、独立样本单位、批次和注释版本。示例的原始数值、基因集、阈值、比较方向、名字和随机种子不是通用默认值。公共数据整理后的 feature_id 表头可直接进入微阵列模型，不必将探针改名为基因。
