from wikievalops.contracts import EvalCase, EvaluationTrace
from wikievalops.metrics import (
    EvidenceRecallAt5Metric,
    RouteCorrectnessMetric,
    SupportedClaimRateMetric,
)


def _case(**expected):
    return EvalCase.model_validate(
        {
            "case_id": "case-1",
            "task_type": "technical_qa",
            "metric_profile": "technical_qa",
            "input": {"query": "q"},
            "expected": expected,
        }
    )


def _trace(**parts):
    return EvaluationTrace.model_validate(
        {"case_id": "case-1", "system_version": "v1", **parts}
    )


def test_route_correctness_supports_multi_intent():
    result = RouteCorrectnessMetric().evaluate(
        _case(routes=["technical_qa", "commerce_risk"]),
        _trace(route={"selected": ["technical_qa"]}),
    )

    assert result.score == 2 / 3
    assert result.details["recall"] == 0.5


def test_evidence_recall_uses_only_top_five():
    documents = [{"document_id": f"doc-{index}"} for index in range(6)]
    result = EvidenceRecallAt5Metric().evaluate(
        _case(evidence_ids=["doc-0", "doc-5"]),
        _trace(retrieval={"documents": documents}),
    )

    assert result.score == 0.5
    assert result.details["missing"] == ["doc-5"]


def test_claim_requires_non_empty_evidence_present_in_context():
    result = SupportedClaimRateMetric().evaluate(
        _case(),
        _trace(
            context={"items": [{"evidence_id": "fact-1"}]},
            generation={
                "claims": [
                    {"claim_id": "supported", "text": "a", "evidence_ids": ["fact-1"]},
                    {"claim_id": "no-citation", "text": "b", "evidence_ids": []},
                    {"claim_id": "missing", "text": "c", "evidence_ids": ["fact-2"]},
                ]
            },
        ),
    )

    assert result.score == 1 / 3
    assert result.details["unsupported_claims"] == ["no-citation", "missing"]

