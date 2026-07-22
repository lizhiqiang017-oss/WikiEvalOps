from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import EvalCase, EvaluationTrace, MetricResult
from .errors import ConfigurationError


class Metric(ABC):
    """单样本指标接口；新增指标时实现 evaluate 并注册即可。"""

    name: str

    @abstractmethod
    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        pass


def _ratio(numerator: int, denominator: int, *, empty_score: float = 1.0) -> float:
    """安全计算比例，并由调用方明确空集合的业务含义。"""

    return empty_score if denominator == 0 else numerator / denominator


class RouteCorrectnessMetric(Metric):
    """计算单条样本的多标签路由 F1，兼容多意图问题。"""

    name = "route_correctness"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        expected = set(case.expected.routes)
        selected = set(trace.route.selected)
        intersection = expected & selected
        precision = _ratio(len(intersection), len(selected), empty_score=0.0)
        recall = _ratio(len(intersection), len(expected), empty_score=1.0)
        score = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        return MetricResult(
            metric=self.name,
            score=score,
            details={
                "expected": sorted(expected),
                "selected": sorted(selected),
                "precision": precision,
                "recall": recall,
            },
        )


class EvidenceRecallAt5Metric(Metric):
    """检查回答所需的 Gold Evidence 是否进入检索结果前五名。"""

    name = "evidence_recall_at_5"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        expected = set(case.expected.evidence_ids)
        top_five = [document.document_id for document in trace.retrieval.documents[:5]]
        matched = expected & set(top_five)
        score = _ratio(len(matched), len(expected), empty_score=1.0)
        return MetricResult(
            metric=self.name,
            score=score,
            details={
                "expected": sorted(expected),
                "retrieved_top_5": top_five,
                "missing": sorted(expected - matched),
            },
        )


class SupportedClaimRateMetric(Metric):
    """检查原子结论引用的证据是否完整存在于最终上下文。"""

    name = "supported_claim_rate"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        available_evidence = {item.evidence_id for item in trace.context.items}
        claims = trace.generation.claims
        supported_claims = [
            claim.claim_id
            for claim in claims
            if claim.evidence_ids and set(claim.evidence_ids).issubset(available_evidence)
        ]
        score = _ratio(len(supported_claims), len(claims), empty_score=0.0)
        unsupported = [claim.claim_id for claim in claims if claim.claim_id not in supported_claims]
        return MetricResult(
            metric=self.name,
            score=score,
            details={
                "claim_count": len(claims),
                "supported_claims": supported_claims,
                "unsupported_claims": unsupported,
                "available_evidence": sorted(available_evidence),
            },
        )


class RiskLabelCorrectnessMetric(Metric):
    """检查单条电商服务商风险分类是否命中 Gold Label。"""

    name = "risk_label_correctness"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        expected = case.expected.risk_label
        actual = trace.generation.risk_label
        score = float(expected is not None and expected == actual)
        return MetricResult(
            metric=self.name,
            score=score,
            details={"expected": expected, "actual": actual},
        )


class CitationVerifiabilityMetric(Metric):
    """检查输出引用是否都能在本次 Trace 的最终上下文中复验。"""

    name = "citation_verifiability"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        context_ids = {item.evidence_id for item in trace.context.items}
        cited_ids = set(trace.generation.citations)
        for claim in trace.generation.claims:
            cited_ids.update(claim.evidence_ids)
        valid_ids = cited_ids & context_ids
        score = _ratio(len(valid_ids), len(cited_ids), empty_score=0.0)
        return MetricResult(
            metric=self.name,
            score=score,
            details={
                "cited_ids": sorted(cited_ids),
                "verifiable_ids": sorted(valid_ids),
                "unverifiable_ids": sorted(cited_ids - context_ids),
            },
        )


class WikiStructureCompletenessMetric(Metric):
    """检查 Wiki 生成任务是否产出预期结构字段，而不是只给一段散文答案。"""

    name = "wiki_structure_completeness"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        required = set(case.expected.required_structured_fields)
        actual = set(trace.generation.structured_output)
        matched = required & actual
        score = _ratio(len(matched), len(required), empty_score=1.0)
        return MetricResult(
            metric=self.name,
            score=score,
            details={
                "required_fields": sorted(required),
                "actual_fields": sorted(actual),
                "missing_fields": sorted(required - actual),
            },
        )


class BusinessConstraintAccuracyMetric(Metric):
    """用可解释业务规则检查电商决策，避免只看风险标签是否碰巧正确。"""

    name = "business_constraint_accuracy"

    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        results = [
            self._check_constraint(name, case.input.business_data, trace)
            for name in case.expected.business_constraints
        ]
        passed = [name for name, ok in results if ok]
        failed = [name for name, ok in results if not ok]
        score = _ratio(len(passed), len(results), empty_score=1.0)
        return MetricResult(
            metric=self.name,
            score=score,
            details={"passed_constraints": passed, "failed_constraints": failed},
        )

    @staticmethod
    def _check_constraint(name: str, data: dict, trace: EvaluationTrace) -> tuple[str, bool]:
        complaint = float(data.get("complaint_rate", 0))
        resolution = float(data.get("first_resolution_rate", 1))
        response = float(data.get("avg_response_seconds", 0))
        claim_evidence = {
            evidence_id
            for claim in trace.generation.claims
            for evidence_id in claim.evidence_ids
        }
        risk_label = trace.generation.risk_label

        if name == "high_risk_when_multi_bad_signal":
            bad_signal_count = sum((complaint >= 0.15, resolution <= 0.60, response >= 70))
            return name, bad_signal_count >= 2 and risk_label == "high"
        if name == "low_risk_when_all_healthy":
            is_healthy = complaint < 0.03 and resolution >= 0.85 and response <= 30
            return name, is_healthy and risk_label == "low"
        if name == "medium_risk_when_mixed_signal":
            is_mixed = complaint >= 0.05 or resolution < 0.80 or response > 40
            is_high = sum((complaint >= 0.15, resolution <= 0.60, response >= 70)) >= 2
            is_low = complaint < 0.03 and resolution >= 0.85 and response <= 30
            return name, is_mixed and not is_high and not is_low and risk_label == "medium"
        if name == "must_use_response_time":
            return name, "metric:response-time" in claim_evidence
        return name, False


DEFAULT_METRICS: tuple[Metric, ...] = (
    RouteCorrectnessMetric(),
    EvidenceRecallAt5Metric(),
    SupportedClaimRateMetric(),
    RiskLabelCorrectnessMetric(),
    CitationVerifiabilityMetric(),
    WikiStructureCompletenessMetric(),
    BusinessConstraintAccuracyMetric(),
)


@dataclass(frozen=True)
class MetricRegistry:
    """集中管理可执行指标，防止配置中静默引用不存在的指标。"""

    metrics: dict[str, Metric]

    @classmethod
    def default(cls) -> "MetricRegistry":
        return cls({metric.name: metric for metric in DEFAULT_METRICS})

    def resolve(self, names: Iterable[str]) -> list[Metric]:
        resolved: list[Metric] = []
        for name in names:
            metric = self.metrics.get(name)
            if metric is None:
                raise ConfigurationError(f"未知指标：{name}")
            resolved.append(metric)
        return resolved
