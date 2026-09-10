# 小数据扩展示例

这里的 TSV、FastQC 文本和 h5ad 全部为项目生成的合成数据。h5ad 包含 240 个细胞、100 个特征、6 个生物学样本标签和两类已知合成细胞。随机生成种子为 27；它只能检查文件衔接和计算行为，不代表生物学效果。原始计数层是 `counts`，默认矩阵与原始层相同。合成参考表不用于真实注释。

在仓库根目录执行。输入不修改；下列示例写入不存在的新目录／文件。先建立父目录 `demo-output`，使用独立且已安装所需依赖的 Python 环境。

## 两组比较与图表

```bash
mkdir demo-output
python3 skills/two-group-comparison-and-effect-estimation/scripts/compare_groups.py --input examples/expansion/paired.tsv --output demo-output/paired.json --numerator treated --denominator control --unit a.u. --method paired --subject-column subject_id --missing-policy error --scale continuous --confidence .95 --independent-units-declared
python3 skills/bioinformatics-result-visualization/scripts/plot_results.py --kind groups --result demo-output/paired.json --output demo-output/groups-figure
```

预期：4 对合成测量，平均差为 3，95% 区间约为 1.70–4.30。图中连线表示真实提供的配对关系。

## 相关与结果一致性

```bash
python3 skills/correlation-and-association-screening/scripts/analyze_correlations.py --input examples/expansion/correlation.tsv --pairs examples/expansion/pairs.tsv --output demo-output/correlation.json --method spearman --inference permutation --permutations 199 --seed 3 --missing-policy error --scale continuous --independent-units-declared
python3 skills/multi-comparison-result-concordance/scripts/compare_results.py --inputs first=examples/expansion/a.tsv second=examples/expansion/b.tsv --output demo-output/concordance.json --taxon synthetic --namespace synthetic --positive-direction 'treated over control' --effect-scale log2-fold-change --alpha .05 --effect-threshold 1
```

预期：Spearman 系数约 0.829；共同可检验范围内的 Jaccard 为 0.5。未出现与未检验状态分别保存。

## 单细胞小流程

```bash
python3 skills/single-cell-object-io-and-qc/scripts/inspect_single_cell.py --input examples/expansion/small.h5ad --counts-layer counts --assay rna --min-counts 1 --min-genes 2 --output demo-output/qc
python3 skills/single-cell-core-analysis/scripts/run_single_cell.py --input demo-output/qc/checked.h5ad --qc-report demo-output/qc/qc.json --counts-layer counts --hvg 50 --pcs 10 --neighbors 10 --resolution .3 --seed 11 --marker-count 8 --output demo-output/core
python3 skills/single-cell-marker-evidence-review/scripts/review_marker_evidence.py --markers demo-output/core/markers.tsv --reference examples/expansion/reference.tsv --taxon synthetic --tissue synthetic --namespace synthetic --output demo-output/markers.json
python3 skills/single-cell-pseudobulk-aggregation/scripts/aggregate_pseudobulk.py --input demo-output/core/processed.h5ad --samples examples/expansion/samples.tsv --counts-layer counts --cell-type type_A --min-cells 5 --numerator treated --denominator control --independent-samples-declared --output demo-output/pseudobulk
python3 skills/bioinformatics-result-visualization/scripts/plot_results.py --kind embedding --result demo-output/core/embedding.tsv --output demo-output/embedding-figure
python3 skills/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py --reports qc=demo-output/qc/qc.json core=demo-output/core/analysis.json markers=demo-output/markers.json aggregation=demo-output/pseudobulk/aggregation.json --figures embedding=demo-output/embedding-figure --language zh --note 'Synthetic demonstration; no biological conclusion.' --output demo-output/report
```

Marker 结果保持 `needs-review`。汇总使用合成对象里已经存在的 `cell_type` 字段，不会自动采用候选注释。Pseudobulk 输出能交给现有 count-DE helper；必须沿用真实研究的独立样本与模型设计。报告中的来源状态不会因为文件生成成功而被改写。

## 样本表和 FastQC

```bash
python3 skills/bioinformatics-format-and-identifier-validation/scripts/validate_sample_table.py --metadata examples/expansion/samples.tsv --matrix examples/expansion/matrix.tsv --matrix-scale raw-counts --group-column condition --output demo-output/metadata
python3 skills/raw-read-quality-reporting/scripts/summarize_fastqc.py --reports one=examples/expansion/fastqc.txt --library-context 'synthetic short-read example' --output demo-output/fastqc.json
```

## 公共数据入口

GEO helper 的 `--accession GSE... --output NEW.json` 先给出有大小限制的下载计划。目录发现和下载由仓库共享 connector 或已审查的宿主负责；解析时必须声明平台、尺度和样本事实。数据未知时保留 `needs-decision`，不猜测分组。默认不把公共原始数据或其说明文字复制进本示例。
