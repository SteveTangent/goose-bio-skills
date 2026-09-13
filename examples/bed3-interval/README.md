# Same-build BED3：原创微型示例

全部表是本项目原创合成数据（Apache-2.0），参考名 toy-v1，不对应真实物种。
只有几十字节一份，无外部数据下载。contig 顺序故意设为 chr2、chr1；A 含重复
和边界相接区间，便于核对排序、重复数和去重覆盖。输入合计不足 200 字节。

从仓库根目录执行；所有输出路径必须不存在。运算和 QC 仅需 Python 标准库，
图需要 NumPy/Matplotlib。先检查 genomic-intervals 任务包的 doctor。

```bash
python3 skills/genomic-interval-operations/scripts/operate_intervals.py \
  --a examples/bed3-interval/a.bed --b examples/bed3-interval/b.bed \
  --contigs examples/bed3-interval/toy.chrom.sizes --operation intersect \
  --build-a toy-v1 --build-b toy-v1 --contig-build toy-v1 \
  --coordinate-system bed0-half-open --strand-policy ignore --duplicates preserve \
  --output interval-output

python3 skills/chromatin-peak-set-qc/scripts/check_peak_sets.py \
  --contig-sizes examples/bed3-interval/toy.chrom.sizes --contig-build toy-v1 \
  --peak interval-output/result.bed --peak-format bed --peak-build toy-v1 \
  --output interval-peak-qc.json

python3 skills/bioinformatics-result-visualization/scripts/plot_results.py \
  --kind intervals --result interval-output/intervals.json --outcome chr1 \
  --output interval-figure

python3 skills/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py \
  --report intervals=interval-output/intervals.json peak_qc=interval-peak-qc.json \
  --figure interval_map=interval-figure --language zh --output interval-report

python3 skills/genomic-interval-operations/scripts/operate_intervals.py \
  --a examples/bed3-interval/a.bed --contigs examples/bed3-interval/toy.chrom.sizes \
  --operation merge --adjacency bookended --build-a toy-v1 --contig-build toy-v1 \
  --coordinate-system bed0-half-open --strand-policy ignore --duplicates preserve \
  --output merged-intervals
```

相交预期：4 个重叠对；逐行长度和 17 bp，去重后仅 12 bp，trace.tsv 保留 A/B 原行。
A 的重复区间没有被静默删除。合并预期：bookended 产生 2 行（30 bp），overlap-only
产生 3 行（也是 30 bp）；行数不同不代表覆盖不同。边界相接的两个半开区间共享 0 bp。

把 B 换成 disjoint.bed 会得到合法零字节 result.bed；empty.bed 也是合法输入。
空结果直接报告，现有峰集 QC 要求非空，不继续调用该步骤。把 build-b 改为其他
版本、坐标改为一基闭区间、链方向改为 same 都应要求澄清；不自行转换数据。
重复策略 reject 会拒绝本例 A；超出 contig 的坐标或额外 BED6 列应拒绝。

图仅显示明确选中的 chr1，完整汇总仍包含两个 contig。几何相交/合并不等于
共识峰、最近基因、重复性或显著性。这些小表检查不代表真实全基因组性能或科学基准。
