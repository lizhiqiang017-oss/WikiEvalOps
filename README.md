# WikiEvalOps

WikiEvalOps 是一个面向企业知识智能系统的全链路评测框架。项目以标准化 Trace 为核心，不绑定具体的 RAG、Agent、向量数据库或记忆框架，因此既可以评测离线运行记录，也可以通过 Adapter 接入真实系统。

当前仓库完成了第一轮最小闭环：

- 定义严格、可版本化的评测样本和全链路 Trace 数据契约；
- 校验 JSONL Benchmark 与离线 Trace；
- 根据任务类型选择对应指标，避免所有样本执行全部指标；
- 实现路由、证据召回、结论证据支持率和电商风险判断等确定性指标；
- 在数据集层聚合路由 Macro-F1 和高风险召回率；
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
                    JSON Run Artifact
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
  --output artifacts/runs/reference-v1.json
```

示例 `reference-v1` 故意包含回归问题，因此 `wikieval run` 会返回退出码 `2`。CLI 退出码可直接用于 CI：

- `0`：评测完成，全部阈值通过；
- `1`：输入数据或配置无效；
- `2`：评测完成，但至少一个质量阈值未通过。

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

## Artifact 可复现性

每次运行都会记录：

- UTC 运行 ID；
- 被测系统版本；
- Benchmark 的绝对路径和 SHA-256；
- 生效配置的 SHA-256；
- 单样本指标、阈值结果和诊断证据；
- 聚合指标、任务切片、失败样本和缺失 Trace 数量。

Artifact 先写入临时文件，再原子替换目标文件，避免 CI 中断时留下不完整的评测结果。

## 后续实现计划

第二轮已经完成 Reference Pipeline v1/v2、规则优先的阶段级错误归因，以及 Baseline/Candidate 版本对比。

运行两个 Reference Pipeline：

```powershell
wikieval run-reference `
  --dataset benchmarks/smoke/cases.jsonl `
  --config configs/evaluation.json `
  --version reference-v1 `
  --output artifacts/runs/reference-pipeline-v1.json

wikieval run-reference `
  --dataset benchmarks/smoke/cases.jsonl `
  --config configs/evaluation.json `
  --version reference-v2 `
  --output artifacts/runs/reference-pipeline-v2.json
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

1. 增加正式质量门禁配置和 Baseline/Candidate 自动拦截策略。
2. 增加基于开源代码的 Fact/File/System Wiki Grounding 样本。
3. 扩展合成电商推荐和满意度诊断场景。
4. 增加 Context、Memory 消融和故障注入。
5. 在确定性评测内核稳定后，增加 Mutation Testing 和 Challenge Set 持续演进。
