# 三个轻量流程模板

这些 JSON 是给 Agent 改写的起始模板，不是自动执行配置。它们不含数据或命令，不改变 Skill 包数量。

| 模板 | 最小流程 | 真实输入需修改 |
| --- | --- | --- |
| `basic-statistics.json` | 配对比较 → 图表 → 报告 | 文件、设计/参数、数值单位、配对字段和组名 |
| `public-expression.json` | 单平台矩阵准备 → 保留缺项的报告 | GSE/GPL、矩阵文件、实际尺度和样本事实 |
| `single-cell.json` | 原始计数 QC → core → embedding 图 → 报告 | 原始层、QC 阈值、独立样本字段和探索参数 |

先在一个新的分析目录放入选定模板（命名为 `analysis.json`）和输入文件。所有路径相对这个目录；只有被当前步骤列为 required_facts 的项才需要先确认。示例阈值不应未经核对就套用于真实研究。

仓库已有可重复使用的小合成输入：[`paired.tsv`](../expansion/paired.tsv) 和 [`small.h5ad`](../expansion/small.h5ad)。复制到分析目录后分别命名为 `data.tsv` 和 `data.h5ad`。合成对象为 240 个细胞 × 100 个特征；其已知实验声明只用于软件检查。

操作、澄清方式、回执与恢复规则见 [流程指南](../../docs/analysis-workflow.md)。实际计算调用 [扩展示例](../expansion/README.md) 中的原有 helper，输出名字调整到模板的 `result`/`outputs`。本工具不会执行这些计算。

公共表达模板中的 GSE1/GPL1 是占位编号，不表示示例取自该公共研究。流程实验另用项目原创的 2 特征 × 2 样本 Series Matrix 形状文本检查接口，保留未知尺度和分组，不进行公共研究的生物学解释。
