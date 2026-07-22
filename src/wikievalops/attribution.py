from __future__ import annotations

from dataclasses import dataclass

from .contracts import EvalCase, EvaluationTrace, FailureAttribution, MetricResult


FAILURE_RECOMMENDATIONS = {
    "route_mismatch": "检查意图分类规则、多意图拆分和路由置信度阈值。",
    "retrieval_miss": "检查知识源索引、召回配置和查询改写策略。",
    "context_assembly_loss": "检查检索结果过滤、去重和上下文预算分配。",
    "unsupported_generation": "收紧证据约束，要求每个原子结论显式绑定上下文证据。",
    "business_decision_error": "检查风险阈值、边界样本和高风险零退化规则。",
    "trace_missing": "检查 Trace 采集链路、case_id 关联和任务执行状态。",
    "trace_invalid": "检查 Adapter 输出协议和 case_id 一致性。",
}


@dataclass(frozen=True)
class AttributionEngine:
    """使用确定性规则定位首个失败阶段，并保留后续连带问题。"""

    def analyze(
        self,
        case: EvalCase,
        trace: EvaluationTrace | None,
        metric_results: list[MetricResult],
        trace_status: str = "ok",
    ) -> FailureAttribution:
        if trace_status != "ok" or trace is None:
            failure = "trace_missing" if trace_status == "missing" else "trace_invalid"
            return FailureAttribution(
                primary_failure=failure,
                evidence=[f"trace_status={trace_status}"],
                recommendation=FAILURE_RECOMMENDATIONS[failure],
            )

        metrics = {result.metric: result for result in metric_results}
        failures: list[tuple[str, str]] = []

        route = metrics.get("route_correctness")
        if route is not None and route.passed is False:
            failures.append(
                (
                    "route_mismatch",
                    f"期望路由={route.details.get('expected')}，实际路由={route.details.get('selected')}",
                )
            )

        retrieval = metrics.get("evidence_recall_at_5")
        if retrieval is not None and retrieval.passed is False:
            failures.append(
                (
                    "retrieval_miss",
                    f"Top-5 缺失证据={retrieval.details.get('missing')}",
                )
            )

        # Gold Evidence 已被检索但没有进入 Context 时，属于上下文组装问题。
        if retrieval is not None and retrieval.score == 1.0:
            context_ids = {item.evidence_id for item in trace.context.items}
            missing_context = sorted(set(case.expected.evidence_ids) - context_ids)
            if missing_context:
                failures.append(("context_assembly_loss", f"Context 缺失证据={missing_context}"))

        supported_claims = metrics.get("supported_claim_rate")
        if supported_claims is not None and supported_claims.passed is False:
            failures.append(
                (
                    "unsupported_generation",
                    f"无有效证据结论={supported_claims.details.get('unsupported_claims')}",
                )
            )

        risk = metrics.get("risk_label_correctness")
        if risk is not None and risk.passed is False:
            failures.append(
                (
                    "business_decision_error",
                    f"期望风险={risk.details.get('expected')}，实际风险={risk.details.get('actual')}",
                )
            )

        if not failures:
            return FailureAttribution()

        primary, primary_evidence = failures[0]
        return FailureAttribution(
            primary_failure=primary,
            secondary_failures=[failure for failure, _ in failures[1:]],
            evidence=[primary_evidence, *[evidence for _, evidence in failures[1:]]],
            recommendation=FAILURE_RECOMMENDATIONS[primary],
        )
