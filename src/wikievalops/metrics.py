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


DEFAULT_METRICS: tuple[Metric, ...] = (
    RouteCorrectnessMetric(),
    EvidenceRecallAt5Metric(),
    SupportedClaimRateMetric(),
    RiskLabelCorrectnessMetric(),
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
