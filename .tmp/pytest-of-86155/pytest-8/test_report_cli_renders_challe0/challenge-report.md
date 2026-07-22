# 挑战集报告

- 源样本数：15
- 挑战样本数：15
- 跳过样本数：0
- 源数据集：C:\Users\86155\Desktop\简历\WikiEvalOps\benchmarks\smoke\cases.jsonl
- 输出数据集：C:\Users\86155\Desktop\简历\WikiEvalOps\artifacts\challenges\round6-challenge.jsonl

## 变异类型
- business_distractor：1
- cross_domain_distractor：1
- generic_distractor：3
- policy_distractor：4
- technical_distractor：5
- workflow_distractor：1

## 分层分布
- challenge：15

## 变异记录
- challenge-route-001 ← route-001 | generic_distractor | 保留原任务主线的同时增加无关干扰，作为基础挑战样本。
- challenge-route-002 ← route-002 | generic_distractor | 保留原任务主线的同时增加无关干扰，作为基础挑战样本。
- challenge-qa-001 ← qa-001 | policy_distractor | 在技术问答中加入文件政策干扰，测试引用定位和路由稳定性。
- challenge-qa-002 ← qa-002 | policy_distractor | 在技术问答中加入文件政策干扰，测试引用定位和路由稳定性。
- challenge-risk-001 ← risk-001 | technical_distractor | 在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。
- challenge-risk-002 ← risk-002 | technical_distractor | 在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。
- challenge-risk-003 ← risk-003 | technical_distractor | 在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。
- challenge-qa-003 ← qa-003 | policy_distractor | 在技术问答中加入文件政策干扰，测试引用定位和路由稳定性。
- challenge-route-003 ← route-003 | generic_distractor | 保留原任务主线的同时增加无关干扰，作为基础挑战样本。
- challenge-qa-004 ← qa-004 | policy_distractor | 在技术问答中加入文件政策干扰，测试引用定位和路由稳定性。
- challenge-risk-004 ← risk-004 | technical_distractor | 在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。
- challenge-risk-005 ← risk-005 | technical_distractor | 在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。
- challenge-wiki-fact-001 ← wiki-fact-001 | cross_domain_distractor | 让事实抽取问题同时出现文件政策干扰，测试事实库路由的纯度。
- challenge-wiki-file-001 ← wiki-file-001 | workflow_distractor | 把文件 Wiki 和系统 Wiki 语义混在一起，测试结构化文件归因能力。
- challenge-wiki-system-001 ← wiki-system-001 | business_distractor | 把系统链路问题和业务风险判断混在一起，测试多意图路由和结构输出。
