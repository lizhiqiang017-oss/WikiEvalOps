from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .contracts import (
    DatasetSplit,
    EvalEvolutionCandidate,
    EvalEvolutionReport,
    FailurePattern,
    RunArtifact,
)


FAILURE_ACTIONS = {
    "route_mismatch": {
        "severity": "medium",
        "action": "生成多意图、干扰意图和边界路由 challenge case。",
        "candidate_type": "add_challenge_case",
        "target_split": DatasetSplit.CHALLENGE,
        "suggested_change": {"mutation_focus": "multi_intent_routing"},
    },
    "retrieval_miss": {
        "severity": "high",
        "action": "生成同义改写、证据稀疏和跨知识库 challenge case。",
        "candidate_type": "add_challenge_case",
        "target_split": DatasetSplit.CHALLENGE,
        "suggested_change": {"mutation_focus": "retrieval_recall"},
    },
    "context_assembly_loss": {
        "severity": "high",
        "action": "增加上下文组装审计样本，检查去重、截断和 token 预算。",
        "candidate_type": "needs_human_review",
        "target_split": None,
        "suggested_change": {"review_focus": "context_budget_and_filtering"},
    },
    "unsupported_generation": {
        "severity": "high",
        "action": "将证据绑定和引用可复验作为生成链路门禁候选。",
        "candidate_type": "raise_quality_gate",
        "target_split": None,
        "suggested_change": {"gate_metric": "supported_claim_rate"},
    },
    "business_decision_error": {
        "severity": "high",
        "action": "生成电商服务边界样本，覆盖多指标共同恶化场景。",
        "candidate_type": "add_challenge_case",
        "target_split": DatasetSplit.CHALLENGE,
        "suggested_change": {"mutation_focus": "business_boundary_rules"},
    },
    "trace_missing": {
        "severity": "high",
        "action": "优先修复 Trace 采集链路，避免缺失 Trace 污染演进结论。",
        "candidate_type": "needs_human_review",
        "target_split": None,
        "suggested_change": {"review_focus": "trace_collection"},
    },
    "trace_invalid": {
        "severity": "high",
        "action": "优先修复 Adapter 输出协议，避免错误 Trace 污染评测结论。",
        "candidate_type": "needs_human_review",
        "target_split": None,
        "suggested_change": {"review_focus": "trace_schema"},
    },
}


@dataclass(frozen=True)
class EvalEvolutionPlanner:
    """根据失败归因生成演进建议；只产出候选项，不直接修改数据集。"""

    def plan(self, artifact: RunArtifact) -> EvalEvolutionReport:
        cases_by_failure: dict[str, list] = defaultdict(list)
        for case in artifact.cases:
            failure_types = []
            if case.attribution.primary_failure:
                failure_types.append(case.attribution.primary_failure)
            failure_types.extend(case.attribution.secondary_failures)
            for failure_type in dict.fromkeys(failure_types):
                cases_by_failure[failure_type].append(case)

        patterns = [
            self._build_pattern(failure_type, failed_cases)
            for failure_type, failed_cases in sorted(cases_by_failure.items())
        ]
        candidates = [
            candidate
            for pattern in patterns
            for candidate in self._build_candidates(pattern, artifact)
        ]
        return EvalEvolutionReport(
            source_run_id=artifact.metadata.run_id,
            source_system_version=artifact.metadata.system_version,
            source_dataset_path=artifact.metadata.dataset_path,
            source_dataset_sha256=artifact.metadata.dataset_sha256,
            case_count=artifact.metadata.case_count,
            status="review_required" if candidates else "ok",
            failure_pattern_count=len(patterns),
            candidate_count=len(candidates),
            failure_patterns=patterns,
            candidates=candidates,
            summary={
                "top_failure_types": {
                    pattern.failure_type: pattern.case_count
                    for pattern in sorted(patterns, key=lambda item: (-item.case_count, item.failure_type))
                },
                "review_policy": "候选项默认 pending_review，不自动写入 Benchmark、Gold Label 或质量门禁。",
            },
        )

    def _build_pattern(self, failure_type: str, failed_cases: list) -> FailurePattern:
        rule = FAILURE_ACTIONS.get(failure_type, self._default_rule(failure_type))
        evidence = [
            item
            for case in failed_cases
            for item in case.attribution.evidence[:2]
        ]
        return FailurePattern(
            pattern_id=f"pattern-{failure_type}",
            failure_type=failure_type,
            severity=rule["severity"],
            case_count=len(failed_cases),
            case_ids=sorted(case.case_id for case in failed_cases),
            evidence=evidence[:6],
            suggested_action=rule["action"],
        )

    def _build_candidates(
        self,
        pattern: FailurePattern,
        artifact: RunArtifact,
    ) -> list[EvalEvolutionCandidate]:
        rule = FAILURE_ACTIONS.get(pattern.failure_type, self._default_rule(pattern.failure_type))
        candidates = [
            EvalEvolutionCandidate(
                candidate_id=f"candidate-{pattern.failure_type}-review",
                source_case_ids=pattern.case_ids,
                candidate_type=rule["candidate_type"],
                target_split=rule["target_split"],
                reason=pattern.suggested_action,
                suggested_change={
                    **rule["suggested_change"],
                    "failure_type": pattern.failure_type,
                    "case_count": pattern.case_count,
                },
            )
        ]
        high_risk_cases = [
            case.case_id
            for case in artifact.cases
            if case.case_id in pattern.case_ids
            and case.risk_level in {"high", "critical"}
        ]
        if high_risk_cases:
            candidates.append(
                EvalEvolutionCandidate(
                    candidate_id=f"candidate-{pattern.failure_type}-frozen-core",
                    source_case_ids=sorted(high_risk_cases),
                    candidate_type="promote_to_frozen_core",
                    target_split=DatasetSplit.FROZEN_CORE,
                    reason="高风险失败样本建议经 review 后进入 frozen_core。",
                    suggested_change={
                        "failure_type": pattern.failure_type,
                        "risk_policy": "protect_high_risk_regression",
                    },
                )
            )
        return candidates

    @staticmethod
    def _default_rule(failure_type: str) -> dict:
        return {
            "severity": "medium",
            "action": f"未知失败类型 {failure_type} 需要人工复核。",
            "candidate_type": "needs_human_review",
            "target_split": None,
            "suggested_change": {"review_focus": failure_type},
        }
