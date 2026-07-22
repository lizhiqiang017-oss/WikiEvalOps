# 对比报告：reference-v1 → reference-v2

- 结论：mixed
- 数据集 SHA-256：ed4829af86dd62a1b17f425f40f2d95d9da6604f46e8df96d3968f1753d28762

## 核心指标变化
- high_risk_recall：0.6667 → 1.0000（+0.3333）
- route_macro_f1：0.7238 → 0.6520（-0.0718）

## 常规指标变化
- business_constraint_accuracy：0.7000 → 1.0000（+0.3000）
- citation_verifiability：0.2857 → 1.0000（+0.7143）
- evidence_location_coverage：0.9167 → 1.0000（+0.0833）
- evidence_recall_at_5：0.9167 → 1.0000（+0.0833）
- risk_label_correctness：0.8000 → 1.0000（+0.2000）
- route_correctness：0.7111 → 0.5778（-0.1333）
- supported_claim_rate：0.5556 → 1.0000（+0.4444）
- wiki_structure_completeness：0.6944 → 1.0000（+0.3056）

## 样本变化
- 修复样本：challenge-route-002, challenge-wiki-system-001
- 退化样本：challenge-risk-001, challenge-risk-002, challenge-risk-004
- 持续失败样本：challenge-qa-001, challenge-qa-002, challenge-qa-003, challenge-qa-004, challenge-risk-003, challenge-risk-005, challenge-wiki-fact-001, challenge-wiki-file-001

## 失败类别变化
- business_decision_error：-1
- route_mismatch：+6
