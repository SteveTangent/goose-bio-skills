# RT-qPCR 与独立 2×2 的小数据示例

所有输入是本项目原创合成表（Apache-2.0），用于计算与交接检查，无患者数据、无外部数据下载。8 个独立生物对象、2 个目标、2 个参考 assay、每项 3 个技术重复，共 96 孔。输入总量不足 10 KB。合成的验证声明仅用于走通接口，不能替代真实实验的扩增效率、内参稳定性、定量范围与对照记录。

从仓库根目录执行，输出目录必须不存在。qPCR 计算仅需 Python 标准库；图需要 NumPy/Matplotlib；分类比较使用 requirements-statistics.txt 的 SciPy 1.17.1。可先用 manage_skills.py doctor 检查 qpcr-results 或 basic-statistics。

```bash
python3 skills/qpcr-relative-expression-and-qc/scripts/analyze_qpcr.py \
  --cq examples/qpcr-categorical/cq.tsv \
  --samples examples/qpcr-categorical/samples.tsv \
  --assays examples/qpcr-categorical/assays.tsv \
  --design examples/qpcr-categorical/design.json --output qpcr-output

python3 skills/bioinformatics-result-visualization/scripts/plot_results.py \
  --kind qpcr --result qpcr-output/qpcr.json --outcome T1 --output qpcr-figure

python3 skills/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py \
  --report qpcr=qpcr-output/qpcr.json --figure T1=qpcr-figure \
  --language zh --output qpcr-report

python3 skills/independent-2x2-categorical-comparison/scripts/compare_2x2.py \
  --table examples/qpcr-categorical/counts.tsv --numerator exposed --denominator reference \
  --event-label response --nonevent-label no-response --independent \
  --sampling-design case-control --output categorical-output

python3 skills/bioinformatics-result-visualization/scripts/plot_results.py \
  --kind categorical --result categorical-output/comparison.json --output categorical-figure

python3 skills/bioinformatics-qc-and-publication-reporting/scripts/build_analysis_report.py \
  --report comparison=categorical-output/comparison.json --figure counts=categorical-figure \
  --language zh --output categorical-report
```

qPCR 预期：treated 的 T1 相对表达为 4，T2 为 0.5；control 各目标为 1。参考量和校准组采用几何平均，计算在 log2 尺度进行。每个点是一个对象，技术孔不增加 n。将 T1 扩增因子改为 1.9 后，treated 的组几何平均应为 3.61；这时不允许选择 delta-delta-cq。扩增因子 1.9 对应约 90% 效率。

2×2 预期：表 [[1,9],[11,3]] 的双侧 Fisher p 约 0.00275946，条件 OR 约 0.0372091，95% 条件精确区间约 [0.000636003,0.425866]。OR 表示 exposed 相对 reference 的事件优势比，不是风险比。counts-zero.tsv 和 counts-separation.tsv 分别保留零与无穷 OR，不加 0.5。病例对照抽样不据此报告总体风险。

未检出孔的 cq 留空、status 填 undetermined；它会产生待澄清 QC 并阻止相对量输出，不自动填 40。缺失参考孔、技术重复超出声明阈值、多个运行、重复 subject 或未知验证依据同样不继续定量。分类表整行/列为零或独立性/抽样设计未明确时不生成效应估计。一个表的 Fisher 检验与条件精确区间使用不同双侧约定，阈值结论不保证完全一致。

这些是有限小数据计算检查；不包含 qPCR 组间显著性检验、效率不确定性传播、临床解释或真实用户基准。入口与 schema 细节见各 Skill 的 references/local-adapter.md。
