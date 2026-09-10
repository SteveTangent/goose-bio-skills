# 从任务开始

仓库有 56 个独立 Skill。通常只装当前任务需要的几个，安装工具会补齐 manifest 声明的依赖。

| 任务包 | 适合的起点 | 交付 |
| --- | --- | --- |
| `rnaseq-results` | 已有计数或差异结果 | 映射、富集、火山图/PCA/热图、汇总报告 |
| `single-cell-qc` | 已有单细胞对象 | 对象与 QC 指引、结果汇总；不包含自动细胞注释 |
| `basic-statistics` | 连续测量与已有结果表 | 两组效应、相关、结果一致性与图表 |
| `public-expression` | 一个公共表达矩阵 | 平台与尺度检查、样本表、结果报告 |
| `single-cell-practical` | 小型 RNA h5ad | QC、探索性聚类、候选证据、按样本汇总与报告 |
| `evidence-review` | 文献或公共记录问题 | 检索、标识符处理与证据追溯 |

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
