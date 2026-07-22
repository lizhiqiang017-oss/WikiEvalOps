from wikievalops.contracts import EvalCase, EvaluationTrace
from wikievalops.metrics import (
    BusinessConstraintAccuracyMetric,
    CitationVerifiabilityMetric,
    EvidenceRecallAt5Metric,
    RouteCorrectnessMetric,
    SupportedClaimRateMetric,
    WikiStructureCompletenessMetric,
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


def test_citation_verifiability_requires_context_evidence():
    result = CitationVerifiabilityMetric().evaluate(
        _case(evidence_ids=["fact-1"]),
        _trace(
            context={"items": [{"evidence_id": "fact-1"}]},
            generation={
                "claims": [
                    {"claim_id": "ok", "text": "a", "evidence_ids": ["fact-1"]},
                    {"claim_id": "bad", "text": "b", "evidence_ids": ["fact-2"]},
                ],
                "citations": ["fact-1", "fact-2"],
            },
        ),
    )

    assert result.score == 0.5
    assert result.details["unverifiable_ids"] == ["fact-2"]


def test_wiki_structure_checks_required_fields():
    result = WikiStructureCompletenessMetric().evaluate(
        _case(required_structured_fields=["summary", "effective_rules", "source_evidence_ids"]),
        _trace(generation={"structured_output": {"summary": "s", "effective_rules": []}}),
    )

    assert result.score == 2 / 3
    assert result.details["missing_fields"] == ["source_evidence_ids"]


def test_business_constraints_check_risk_reasoning():
    result = BusinessConstraintAccuracyMetric().evaluate(
        EvalCase.model_validate(
            {
                "case_id": "risk-1",
                "task_type": "commerce_risk",
                "metric_profile": "commerce_risk",
                "input": {
                    "query": "评估服务商风险。",
                    "business_data": {
                        "complaint_rate": 0.18,
                        "first_resolution_rate": 0.55,
                        "avg_response_seconds": 82,
                    },
                },
                "expected": {
                    "risk_label": "high",
                    "business_constraints": [
                        "high_risk_when_multi_bad_signal",
                        "must_use_response_time",
                    ],
                },
            }
        ),
        _trace(
            generation={
                "risk_label": "high",
                "claims": [
                    {"claim_id": "response", "text": "响应时间过长", "evidence_ids": ["metric:response-time"]}
                ],
            }
        ),
    )

    assert result.score == 1.0
