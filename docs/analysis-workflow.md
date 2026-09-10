# 从问题到可以继续的分析

这个可选的仓库工具连接已有 Skill：保存已经确认的事实，检查结果能否沿用，并提供一份图表、方法和未解决事项的入口。它不会执行分析命令、安装依赖、下载数据或修改旧结果。单个 Skill 仍可独立使用；复制单个 Skill 不会安装此工具。

## 用户从哪里开始

| 已有输入 | 想回答的问题 | 当前起点 | 首先核对什么 |
| --- | --- | --- | --- |
| 连续测量表 | 两组相差多少？ | 两组比较 → 图表 → 报告 | 配对关系、独立样本单位、数值尺度与比较方向 |
| 已有两组比较 JSON | 把结果画出来并整理方法 | 直接从图表开始 | 原始结果是否由当前适配器生成，输入和版本是否匹配 |
| 单个平台的 GEO Series Matrix | 整理成可用矩阵和样本表 | 公共表达准备 → 报告 | 平台；分组和尺度未知时可以先检查并列出缺项 |
| 小型 RNA h5ad 与原始 counts 层 | 做 QC 与探索性聚类 | QC → core → 图表 → 报告 | 实验类型、原始计数来源和独立样本字段 |
| 已检查的 h5ad 和对应 QC JSON | 接着做探索性分析 | 直接从 core 开始 | QC 凭据必须匹配对象，保留所需来源文件与事实依据 |
| 已有当前分析结果 | 接着整理交付 | 报告或结果入口 | 保留原生结果状态；报告写完不等于分析问题都已解决 |

三个起始模板见 [基础统计](../examples/workflow/basic-statistics.json)、[公共表达](../examples/workflow/public-expression.json)、[单细胞](../examples/workflow/single-cell.json)。示例路径、参数和 GSE/GPL 编号是占位或合成设置，必须根据实际输入修改；不会自动选出统计方法或数据集。

从中途开始时，只保留需要的步骤，移除不再执行的前置步骤及其依赖；把已有产物作为输入。已有事实的依据仍需可读取。工具会重新核对原生输入校验值、参数和版本，旧步骤的回执不能直接冒充这个新起点的回执。无需重跑已经由现有对象和凭据充分支持的上游分析。

## 面向 Agent 的交互规则

1. 先检查已有文件与对话事实。只有多步骤工作需要保存和交接时，才使用本流程；单次简单任务不增加额外表单。
2. 在独立分析目录里创建 `analysis.json`，由 Agent 根据模板填写步骤、参数和路径。用户无需阅读或填写整份 JSON。
3. 运行 `status`，只向用户表达 `next_action` 的第一个关键问题，不把所有字段一次性抛给用户。解释问题为什么影响结果，例如“独立样本”通常指供体或动物，技术重复不能自动增加这个样本数。
4. 用户已确认的信息直接记录；文件能证实的信息记录具体字段、生成步骤或出处。`file` 表示记录者依据文件提出的事实，不是工具自动完成的语义验证。未知项保持未知，不能根据文件名猜组别。
5. 完成需要的澄清后调用原来的 Skill，遵守其科学输入和方法要求；运行后登记原生结果，再进入下一步。`ready` 仅表示本交接工具没有发现缺失或失效，不是科学适用性、安装完整性或执行授权的证明。
6. 用结果入口解释已有图表、方法、尚未解决的事项和下一步。若输出是 partial/needs-decision/needs-review，报告可以汇总它，但后续分析不能将它当作完成结果。

## 最小文件约定

`analysis.json` 包含题目、少量事实和最多 12 个按依赖顺序排列的步骤。它不存储命令或可执行代码。

- **事实**：值、`user/file/unknown` 来源、简短说明，以及适用输入的校验值。文件变化或丢失会要求重新确认。只检查当前步骤声明需要的事实，其他字段可以暂时未知。
- **步骤**：现有 Skill、原生输入校验字段对应的文件、参数、依赖、原生结果、要保留的产物和新回执路径。`fact_parameters` 将参数绑定到已确认事实，发现尺度或组名冲突时暂停。
- **回执**：原生结果状态、实际工具版本、输入/输出校验值，以及当时使用的事实、参数、包版本和依赖身份。它是本地记录，不是不可伪造的执行证明。

所有数据路径相对于计划所在目录，支持文件不超过 16 MiB、JSON 不超过 1 MiB 的小项目。路径不得越界或经过符号链接。新文件的父目录须已存在；回执、确认后的计划和概览只写入新文件，不覆盖旧文件。确认后的计划必须与原计划位于同一目录，以保持输入相对路径的含义。面向当前 Linux/macOS 环境，未验证 Windows。

## 常用操作

以下命令从仓库根目录调用。假设计划位于 `PROJECT/analysis.json`，数据文件位于该项目内。

```bash
python3 scripts/manage_workflow.py status --plan PROJECT/analysis.json

python3 scripts/manage_workflow.py confirm --plan PROJECT/analysis.json \
  --fact scale --value '"continuous"' --source user \
  --note '用户确认原始测量为连续值，单位见实验记录' \
  --evidence data.tsv --output analysis-confirmed-1.json

# 后续使用返回的新计划文件；重复 confirm 时串联上一个新计划，保留已有答案。
python3 scripts/manage_workflow.py status --plan PROJECT/analysis-confirmed-1.json

# 在该项目目录运行实际 Skill；原生输出路径必须与计划一致。
python3 scripts/manage_workflow.py record --plan PROJECT/analysis-confirmed-1.json --step compare

python3 scripts/manage_workflow.py overview --plan PROJECT/analysis-confirmed-1.json --output overview-1.md
```

`--value` 使用 JSON 值。一个事实可绑定多个输入文件；这些文件界定该事实的适用数据，并不自动证明事实正确。`tool_versions` 可填写确实需要固定的运行库版本；工具核对原生输出中的版本，不自动探测整个环境。环境准备继续使用 [doctor 和任务包](task-bundles.md)。

目前核对八种原生 helper 结果：两组比较、公共表达准备、单细胞 QC/core、marker 证据、pseudobulk、图表和报告。其他适配器需先实现并检查其结果格式，不能仅填一个 Skill 名就冒充支持。

## 中断后如何继续

重新运行 `status`。已完成且输入、事实、参数、包身份、运行库版本要求、依赖回执和产物仍匹配的步骤可沿用。参数或输入改变时，该步骤及依赖它的分析不再沿用。工作环境的库版本若发生变化，应更新 `tool_versions`；工具不会在后台自动监测环境。

若外部工具失败且没有原生结果，可记录明确标注为“用户/Agent 报告的失败”：

```bash
python3 scripts/manage_workflow.py note-failure --plan PROJECT/analysis.json \
  --step compare --note '计算工具启动失败，尚未产生结果'
```

重试时，把该步骤的 `receipt` 改成新的名字，例如 `compare-receipt-2.json`。需要重算时也将 `result`、`outputs` 及下游 `inputs` 改为新输出路径。完成实际计算后再 `record`，不通过手改旧回执状态宣告成功。旧回执与产物保留，只有更改了依赖的下游步骤需要重新检查。

输出变化在 `status` 时才被检测；概览是生成时的快照。多人并发修改目录、自动任务调度、日志服务和任意工作流插件不在本工具范围内。数据、事实和失败说明保持本地，不自动上传研究项目。
