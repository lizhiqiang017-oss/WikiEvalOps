# Eval 轻量自进化

WikiEvalOps 的 Eval 自进化采用“失败驱动分析、人工审核准入”的方式，目标是让评测体系能够吸收线上失败，但不让一次错误运行直接改变正式 Benchmark。

```text
Run Artifact
    ↓
Failure Attribution
    ↓
Failure Pattern 聚类
    ↓
Evolution Candidate
    ↓
人工 Review
    ↓
Challenge / Frozen Core / Quality Gate
```

运行命令：

```powershell
wikieval evolve `
  --artifact artifacts/runs/round5-reference-v1.json `
  --output artifacts/evolution/round11-evolution-report.json
```

输入是一次已经完成的 Run Artifact，输出是带有数据集摘要、失败模式、证据和候选动作的 JSON 报告。报告可以被保存、审阅和回放，不依赖模型 API。

候选动作包括：

- `add_challenge_case`：把路由、检索或电商业务边界失败转成挑战样本；
- `promote_to_frozen_core`：对高风险失败样本提出核心回归集晋升建议；
- `raise_quality_gate`：把证据支持率等关键指标提升为质量门禁候选；
- `needs_human_review`：Trace 缺失、协议异常或未知失败类型进入人工排查。

所有候选默认是 `pending_review`，不会自动修改 Benchmark、Gold Label 或质量门禁配置。人工审核时需要确认失败是否来自真实业务边界、Gold Label 是否可复验、新样本是否重复或过拟合，以及变更是否可以回滚。

这是一个有意的工程取舍：完全自动化的收益是迭代速度更快，但代价是错误标签、Benchmark 污染和指标漂移难以及时发现。当前方案牺牲少量人工审核时间，换取评测可信度和可审计性。

面试中可以这样表达：

> 我没有把 Eval 自进化做成自动改 Benchmark 的黑盒，而是让它先从失败 Trace 中聚类失败模式，再生成 challenge case、frozen core 和质量门禁候选，最后由人工审核准入。
