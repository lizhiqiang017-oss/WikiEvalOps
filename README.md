# WikiEvalOps

WikiEvalOps 是一个面向企业知识智能系统的全链路评测框架。项目以标准化 Trace 为核心，不绑定具体的 RAG、Agent、向量数据库或记忆框架，因此既可以评测离线运行记录，也可以通过 Adapter 接入真实系统。

当前仓库已完成前三轮工程闭环：

- 定义严格、可版本化的评测样本和全链路 Trace 数据契约；
- 校验 JSONL Benchmark 与离线 Trace；
- 根据任务类型选择对应指标，避免所有样本执行全部指标；
- 实现路由、证据召回、结论证据支持率和电商风险判断等确定性指标；
- 在数据集层聚合路由 Macro-F1 和高风险召回率；
- 通过数据集级质量门禁输出 `PASS`、`WARN` 或 `BLOCK`；
- 单独保存可回放 Trace，并在 Artifact 中记录路径和 SHA-256；
- 汇总延迟、成本、检索调用和重试等运行效率数据；
- 对失败样本执行阶段级错误归因，并比较 Baseline/Candidate 的指标和失败类型变化；
- 记录不可变运行元数据，并通过原子写入生成 JSON Artifact；
- 提供 CLI、12 条冒烟样本以及不依赖模型 API 的测试。

仓库内的电商数据均为合成数据，不包含任何公司代码、内部配置或生产数据。

## 项目架构

```text
评测样本 EvalCase                    离线 Trace / 在线被测系统
        |                                      |
        v                                      v
  数据集校验器                            Trace Adapter
        |                                      |
        +------------------+-------------------+
                           v
                    Evaluation Harness
                           |
                 任务类型 -> 指标配置
                           |
                    确定性指标注册表
                           |
                 单样本结果 + 聚合结果
                           |
             Trace JSONL + JSON Run Artifact
```

`EvaluationTrace` 保留路由、检索、上下文、记忆、生成以及耗时/成本等阶段信息，为后续阶段级错误归因提供数据基础。对外展示的核心指标保持精简，诊断信息附着在具体失败样本上。

## 快速开始

建议先创建虚拟环境，再以可编辑方式安装项目：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

校验内置 Benchmark 和 Trace：

```powershell
wikieval validate benchmarks/smoke/cases.jsonl
wikieval validate examples/traces/reference-v1.jsonl --kind traces
```

如果只进行仓库内开发、暂时不安装命令行入口，可以设置 `PYTHONPATH=src` 后使用模块方式运行。pytest 已在 `pyproject.toml` 中配置好 `src` 路径。

执行冒烟评测：

```powershell
wikieval run `
  --dataset benchmarks/smoke/cases.jsonl `
  --traces examples/traces/reference-v1.jsonl `
  --config configs/evaluation.json `
  --output artifacts/runs/reference-v1.json `
  --trace-output artifacts/traces/reference-v1.jsonl
```

示例 `reference-v1` 故意包含回归问题，因此 `wikieval run` 会返回退出码 `2`。CLI 退出码可直接用于 CI：

- `0`：评测完成，质量门禁状态为 `PASS` 或 `WARN`；
- `1`：输入数据或配置无效；
- `2`：评测完成，质量门禁状态为 `BLOCK`；
- `3`：版本对比发现退化或混合变化。

运行测试：

```powershell
python -m pytest
```

## 数据契约

`EvalCase` 表示一条评测样本，主要保存：

- 任务类型与风险等级；
- 用户问题及可选会话、业务数据；
- 期望路由；
- 回答所需的 Gold Evidence；
- 必须包含的结论；
- 可选的业务风险标签。

`EvaluationTrace` 表示被测系统对一条样本的完整执行记录，主要保存：

- 实际路由及置信度；
- 检索文档及分数；
- 最终组装的上下文；
- 记忆读取和写入；
- 原子结论、引用和结构化输出；
- 各阶段耗时、成本和运行异常。

所有结论都应显式声明对应的证据 ID。确定性指标 `supported_claim_rate` 只有在结论引用非空、并且所有引用都真实存在于最终上下文时，才将其视为“结构上有证据支持”。后续 LLM Judge 可以继续判断语义蕴含关系，但不能替代这项结构校验。

## 指标设计

每条样本只运行其 `metric_profile` 指定的指标。第一轮包含：

- `route_correctness`：单样本多标签路由 F1；
- `evidence_recall_at_5`：Gold Evidence 出现在前 5 个检索结果中的比例；
- `supported_claim_rate`：具有有效上下文证据的原子结论比例；
- `risk_label_correctness`：单条电商服务商风险标签是否正确。

运行汇总还会计算数据集级 `route_macro_f1` 和 `high_risk_recall`。其余详细信息保留在单样本结果中，避免主看板堆积大量次要指标。

## 质量门禁

逐样本 `metric_thresholds` 用于定位具体失败样本；数据集级 `quality_gates` 才决定版本是否可以进入下一阶段。每个门禁指标配置两条边界：

- 分数不低于 `warn_below`：`PASS`；
- 分数低于 `warn_below`、但不低于 `block_below`：`WARN`；
- 分数低于 `block_below`：`BLOCK`。

关键指标彼此独立判断，不计算可相互抵消的总分。例如高风险召回下降不能由较低成本或较高路由分数抵消。配置要求完整 Trace 时，任一 Trace 缺失或协议无效也会直接触发 `BLOCK`。

## Trace 与效率

`run` 和 `run-reference` 都支持可选的 `--trace-output`。输出采用标准 `EvaluationTrace` JSONL，可被 `validate` 校验，也可通过离线 Adapter 重新计算指标。Artifact 会记录 Trace 绝对路径与 SHA-256，防止回归分析误用其他运行记录。

效率报告只汇总被测系统真实提供的数据，不根据中文字符数伪造 Token 或模型费用，包括：

- 总延迟的均值、P50 和 P95；
- 工具调用、检索调用和重试次数；
- 被测系统提供的 Token 使用量；
- 按成本字段分别统计的总量和均值。

效率数据当前用于版本解释和人工选型，不参与质量总分。

## Artifact 可复现性

每次运行都会记录：

- UTC 运行 ID；
- 被测系统版本；
- Benchmark 的绝对路径和 SHA-256；
- 生效配置的 SHA-256；
- 可选 Trace 文件的绝对路径和 SHA-256；
- 单样本指标、阈值结果和诊断证据；
- 聚合指标、任务切片、失败样本和缺失 Trace 数量。

Artifact 先写入临时文件，再原子替换目标文件，避免 CI 中断时留下不完整的评测结果。

## 第四轮：Wiki 与业务约束评测

第四轮开始补齐更贴近企业 Wiki 与电商服务场景的样本表达能力：

- `EvalCase` 增加 `dataset_split`，用于区分 `smoke`、`frozen_core`、`challenge` 和 `holdout`；
- `EvalCase` 增加 `knowledge_base_type`，用于区分 `fact_wiki`、`file_wiki`、`system_wiki`、`commerce` 和 `mixed`；
- `ExpectedResult` 增加 `required_structured_fields`，用于检查 Wiki 生成结果是否是可落库结构，而不是一段不可治理的自然语言；
- `ExpectedResult` 增加 `business_constraints`，用于描述电商服务商治理中的硬约束。
- `ExpectedResult` 增加 `required_evidence_locations`，用于要求关键证据必须能定位到页码、段落、代码行或业务字段路径。

本轮新增三个确定性指标：

- `citation_verifiability`：检查输出引用是否全部能在本次 Trace 的最终上下文中复验；
- `wiki_structure_completeness`：检查 Fact/File/System Wiki 是否包含预期结构字段；
- `business_constraint_accuracy`：检查电商风险判断是否满足可解释业务约束，例如多项坏信号必须判高风险、高响应时间必须被纳入证据。
- `evidence_location_coverage`：检查关键证据是否携带可人工复验的位置，例如 `repository.py:12`、`售后政策.pdf#page=3` 或 `business_data.avg_response_seconds`。

这些指标不依赖 LLM Judge，因此适合进入回归测试和 CI 门禁。LLM Judge 后续只作为辅助诊断，不决定关键版本的 `PASS/BLOCK`。

当前冒烟集已经覆盖：

- Fact Wiki：事实抽取、实体和来源证据；
- File Wiki：政策文件摘要、生效规则和引用可复验；
- System Wiki：系统节点、链路边和风险控制；
- 电商服务商风险：投诉率、首次解决率、响应时间与风险标签。

## 第五轮：证据定位与分层报告

第五轮把“引用存在”推进到“引用可定位”。`RetrievedDocument` 和 `ContextItem` 都支持 `locations` 字段，当前定位类型包括：

- `page`：适合 PDF、Word 转换后的页码；
- `paragraph`：适合政策、制度、系统文档中的章节或段落；
- `line`：适合代码仓库事实和调用链证据；
- `field_path`：适合电商指标、订单字段、服务商画像字段等结构化业务数据。

运行 Artifact 现在额外输出两类切片：

- `dataset_split_slices`：按 `smoke`、`frozen_core`、`challenge`、`holdout` 聚合指标；
- `knowledge_base_slices`：按 `fact_wiki`、`file_wiki`、`system_wiki`、`commerce`、`mixed` 聚合指标。

这两类切片用于回答更工业化的问题：到底是挑战集退化，还是核心回归集退化；到底是 File Wiki 引用定位失败，还是电商业务约束失败。它们不替代质量门禁，但能显著提升问题归因效率。

## 后续实现计划

第二轮已经完成 Reference Pipeline v1/v2、规则优先的阶段级错误归因，以及 Baseline/Candidate 版本对比。

运行两个 Reference Pipeline：

```powershell
wikieval run-reference `
  --dataset benchmarks/smoke/cases.jsonl `
  --config configs/evaluation.json `
  --version reference-v1 `
  --output artifacts/runs/reference-pipeline-v1.json `
  --trace-output artifacts/traces/reference-pipeline-v1.jsonl

wikieval run-reference `
  --dataset benchmarks/smoke/cases.jsonl `
  --config configs/evaluation.json `
  --version reference-v2 `
  --output artifacts/runs/reference-pipeline-v2.json `
  --trace-output artifacts/traces/reference-pipeline-v2.jsonl
```

比较两个版本：

```powershell
wikieval compare `
  --baseline artifacts/runs/reference-pipeline-v1.json `
  --candidate artifacts/runs/reference-pipeline-v2.json `
  --output artifacts/comparisons/v1-v2.json
```

对比命令会先校验两份 Artifact 的 Benchmark 摘要和评测配置摘要，防止不同数据集或不同评分规则之间产生不可信对比。对比报告包括：

- 核心指标和普通指标变化；
- 已修复样本、新增退化样本和仍未修复样本；
- 路由、检索、上下文、生成和业务决策等失败类型数量变化；
- `improved`、`regressed`、`mixed` 或 `unchanged` 版本结论。

Reference Pipeline 只读取 `query`、`conversation` 和 `business_data`，不会读取 `expected`，避免通过 Gold Label 生成答案导致评测泄漏。它只是一个可复现实验载体，不代表真实生产 Agent。

下一阶段计划：

1. 将 `frozen_core` 扩展到 40 条左右，优先覆盖高频稳定场景。
2. 将 `challenge` 扩展到 40-60 条，专门沉淀线上或面试可讲的困难失败模式。
3. 增加引用定位值的格式校验，例如页码格式、代码行格式和字段路径格式。
4. 增加 CI 审计、基础设施错误隔离和防 Gold Label 泄漏检查。
5. 在确定性评测内核稳定后，增加 Mutation Testing 和受控 Challenge Set 演进。

Context 和 Memory 继续作为标准 Trace 的可观测节点并参与错误归因，但项目不建设专门的消融实验，避免偏离 Wiki 证据质量、电商决策和发布门禁这条主线。
