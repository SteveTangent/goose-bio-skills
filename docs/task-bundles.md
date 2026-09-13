# 从任务开始

仓库有 60 个独立 Skill。通常只装当前任务需要的几个，安装工具会补齐 manifest 声明的依赖。

| 任务包 | 适合的起点 | 交付 |
| --- | --- | --- |
| `rnaseq-results` | 已有计数或差异结果 | 映射、富集、火山图/PCA/热图、汇总报告 |
| `single-cell-qc` | 已有单细胞对象 | 对象与 QC 指引、结果汇总；不包含自动细胞注释 |
| `basic-statistics` | 连续测量与已有结果表 | 两组效应、相关、结果一致性与图表 |
| `public-expression` | 一个公共表达矩阵 | 平台与尺度检查；适用的 log2 微阵列接差异、映射、富集和报告 |
| `single-cell-practical` | 小型 RNA h5ad | QC、探索性聚类、候选证据、按样本汇总与报告 |
| `evidence-review` | 文献或公共记录问题 | 检索、标识符处理与证据追溯 |

已有文件、不确定从哪一步开始时，看 [按输入选择起点和结果交接](analysis-workflow.md)。

这些是安装组合，不是绕过科学澄清的一键流水线。根据当前输入从合适的一步开始，不必强制重跑前面步骤。

```text
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py doctor --bundle rnaseq-results
python3 scripts/manage_skills.py install --bundle rnaseq-results --destination NEW_SKILLS_DIRECTORY
```

`doctor` 仅读取当前 Python/R 环境的依赖信息，不下载、不安装。它显示已覆盖的本地 helper 是否具备基础依赖；`unchecked_helpers` 列出尚未覆盖的 helper，此时不会报告已就绪。指导型 Skill 和超出 helper 范围的其他工具仍需按任务检查。DESeq2 使用时还需要声明实际版本与模型设计。

`install` 需要一个不存在的目标目录，且父目录已经存在；例如已建立分析项目 `.agents` 后，将新目录 `.agents/skills` 作为目标。完整复制包并核对校验值，拒绝覆盖已有安装。已有 Skill 目录请先用新的暂存目录检查，再按宿主的安装方式迁移；不要把不同版本叠加复制。

也可以用 `--skill SKILL_NAME` 选择单个 Skill，重复该参数选择多个。
安装 Skill 不等于安装外部分析工具，也不自动连接共享网络 companion。

## 分析依赖

本地映射、ORA、矩阵交接与 Markdown 报告使用 Python 标准库。作图需要 NumPy、Matplotlib；排序富集需要 GSEApy **1.3.0**、pandas；计数差异需要 R、DESeq2、jsonlite。建议使用独立项目环境，不自动改动用户全局环境。

依赖清单见 [requirements-figures.txt](../requirements-figures.txt) 和 [requirements-enrichment.txt](../requirements-enrichment.txt)。用户选择安装后可用 Python 的包安装工具读取这些文件；本库不会在分析脚本中执行安装。R 环境按 count-DE 的版本契约准备。

先试 [几 KB 的离线示例](../examples/efficiency/README.md)，再接入自己的数据。对话规则与实例见 [用户体验说明](user-experience.md)。

新增统计任务依赖 NumPy、SciPy。小型 h5ad 适配依赖 AnnData、h5py；核心分析还需要 Scanpy 1.12.4 和 igraph 0.11.9。版本清单：[基础统计](../requirements-statistics.txt)、[单细胞](../requirements-single-cell.txt)。示例环境实际使用 Python 3.13；请使用与这些版本兼容的 Python。GEO core 是离线解析器，包安装不会附带仓库级网络 companion。

表达数据可从 [研究问题入口](expression-workflows.md) 开始。微阵列使用 R 4.4.1 / limma 3.60.6；doctor 检查当前 PATH 中 Rscript 的精确版本。将该任务环境的 R 放在 PATH 前部，或执行器显式使用 --rscript；无需覆盖其他 R 安装。安装包不下载参考数据库，已有 ID Skill 可转换已选定的映射 TSV 与 GMT。

## 蛋白组和微生物距离入口

| 任务包 | 已有输入 | 先澄清什么 | 环境与交付 |
| --- | --- | --- | --- |
| protein-results | protein-level 定量 TSV + sample/condition/subject 元数据 | 尺度、归一化依据、零/缺失含义和独立对象；有批次时检查混杂 | QC 为标准库；模型 R 4.4.1 / limma 3.60.6；图需要 NumPy/Matplotlib；输出 QC、差异、图和报告 |
| microbiome-ordination | 完整距离矩阵，或现有整数特征表生成的 beta 距离 | 距离指标、零深度/缺失对、样本分组 | PCoA 需要 NumPy，图需要 Matplotlib；距离计算不作归一化，PCoA 不做组间显著性检验 |

新 QC/PCoA、protein limma 及既有标准库 beta helper 的 doctor 依赖已覆盖。
依赖就绪不代表距离语义或研究设计正确；仍按各 helper 边界检查。试用 [小数据与命令](../examples/protein-pcoa/README.md)。

## qPCR 与分类结局入口

| 任务包 | 已有输入 | 先澄清什么 | 环境与交付 |
| --- | --- | --- | --- |
| qpcr-results | RT-qPCR Cq 长表、样本表、assay 验证表、design.json | 生物对象、内参依据、每周期扩增因子、未检出与校准组 | QC/相对量仅标准库；图需要 NumPy/Matplotlib；每个靶标单独作图，无显著性检验 |
| basic-statistics | 两个独立组的事件/非事件整数计数 | 事件含义、分母、独立性、抽样设计和 OR 方向 | 2×2 helper 固定 SciPy 1.17.1；输出 Fisher 双侧检验与条件 OR/精确区间；零单元格不自动加 0.5 |

这里的 qPCR 是 RNA 逆转录后的相对表达，扩增因子 1.9 表示约 90% 效率。OR 是优势比，不等于风险比；病例对照表不能给出总体发病风险。依赖检查已覆盖两个 helper。[可运行的小表与命令](../examples/qpcr-categorical/README.md)。该批后为 9 个安装任务包；本批加入 genomic-intervals 后共 10 个。

## 同版本基因组区间入口

| 任务包 | 已有输入 | 先澄清什么 | 环境与交付 |
| --- | --- | --- | --- |
| genomic-intervals | 一到两份 exact BED3 + contig-size 表 | 各输入的准确 build、零基半开、忽略链方向、重复保留/拒绝；合并是否包含边界相接 | 运算与峰集 QC 仅标准库，图需要 NumPy/Matplotlib；输出 BED3、原行追溯、去重覆盖、图与报告 |

区间 helper 上限为每表 2,000 行、20,000 个重叠对；图只显示一个明确的 contig、最多 60 行，不静默抽样。空输出是合法结果，直接报告；非空结果才接现有峰集 QC。doctor 仅检查限定 helper 的环境，不声称 bedtools/Gtars/polars-bio 已安装或已验证。[原始小表与命令](../examples/bed3-interval/README.md)。
