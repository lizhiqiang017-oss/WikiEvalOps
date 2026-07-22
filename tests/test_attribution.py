from wikievalops.attribution import AttributionEngine
from wikievalops.contracts import EvalCase, EvaluationTrace, MetricResult


def _case():
    return EvalCase.model_validate(
        {
            "case_id": "case-1",
            "task_type": "technical_qa",
            "metric_profile": "technical_qa",
            "input": {"query": "哪个模块调用存储客户端？"},
            "expected": {"routes": ["technical_qa"], "evidence_ids": ["fact:edge"]},
        }
    )


def test_attribution_uses_first_failed_stage_as_primary():
    metrics = [
        MetricResult(
            metric="route_correctness",
            score=0,
            passed=False,
            details={"expected": ["technical_qa"], "selected": ["commerce_risk"]},
        ),
        MetricResult(
            metric="evidence_recall_at_5",
            score=0,
            passed=False,
            details={"missing": ["fact:edge"]},
        ),
    ]
    result = AttributionEngine().analyze(
        _case(),
        EvaluationTrace(case_id="case-1", system_version="v1"),
        metrics,
    )

    assert result.primary_failure == "route_mismatch"
    assert result.secondary_failures == ["retrieval_miss"]


def test_attribution_detects_context_assembly_loss():
    metrics = [
        MetricResult(
            metric="evidence_recall_at_5",
            score=1,
            passed=True,
            details={"missing": []},
        )
    ]
    result = AttributionEngine().analyze(
        _case(),
        EvaluationTrace(case_id="case-1", system_version="v1", context={"items": []}),
        metrics,
    )

    assert result.primary_failure == "context_assembly_loss"

