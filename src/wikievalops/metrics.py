from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import EvalCase, EvaluationTrace, MetricResult
from .errors import ConfigurationError


class Metric(ABC):
    name: str

    @abstractmethod
    def evaluate(self, case: EvalCase, trace: EvaluationTrace) -> MetricResult:
        pass


def _ratio(numerator: int, denominator: int, *, empty_score: float = 1.0) -> float:
    return empty_score if denominator == 0 else numerator / denominator


class RouteCorrectnessMetric(Metric):
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
    metrics: dict[str, Metric]

    @classmethod
    def default(cls) -> "MetricRegistry":
        return cls({metric.name: metric for metric in DEFAULT_METRICS})

    def resolve(self, names: Iterable[str]) -> list[Metric]:
        resolved: list[Metric] = []
        for name in names:
            metric = self.metrics.get(name)
            if metric is None:
                raise ConfigurationError(f"unknown metric: {name}")
            resolved.append(metric)
        return resolved

