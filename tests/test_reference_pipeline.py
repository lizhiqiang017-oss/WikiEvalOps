from wikievalops.contracts import EvalCase
from wikievalops.reference_pipeline import ReferencePipeline


def _case(expected):
    return EvalCase.model_validate(
        {
            "case_id": "multi-1",
            "task_type": "routing",
            "metric_profile": "routing",
            "input": {"query": "分析服务商风险，并说明相关接口来自哪里。"},
            "expected": expected,
        }
    )


def test_v2_supports_multi_intent_better_than_v1():
    case = _case({"routes": ["commerce_risk", "technical_qa"]})

    assert ReferencePipeline("reference-v1").execute(case).route.selected == ["commerce_risk"]
    assert ReferencePipeline("reference-v2").execute(case).route.selected == ["commerce_risk", "technical_qa"]


def test_pipeline_does_not_read_expected_gold_labels():
    first = ReferencePipeline("reference-v2").execute(_case({"routes": ["technical_qa"]}))
    second = ReferencePipeline("reference-v2").execute(_case({"routes": ["commerce_risk"]}))

    assert first.route == second.route
    assert first.retrieval == second.retrieval
    assert first.generation == second.generation


def test_v2_detects_boundary_high_risk():
    case = EvalCase.model_validate(
        {
            "case_id": "risk-boundary",
            "task_type": "commerce_risk",
            "metric_profile": "commerce_risk",
            "risk_level": "critical",
            "input": {
                "query": "评估服务商风险。",
                "business_data": {
                    "complaint_rate": 0.16,
                    "first_resolution_rate": 0.58,
                    "avg_response_seconds": 75,
                },
            },
            "expected": {"risk_label": "high"},
        }
    )

    assert ReferencePipeline("reference-v1").execute(case).generation.risk_label == "medium"
    assert ReferencePipeline("reference-v2").execute(case).generation.risk_label == "high"


def test_v2_generates_structured_file_wiki():
    case = EvalCase.model_validate(
        {
            "case_id": "wiki-file",
            "task_type": "file_wiki",
            "metric_profile": "file_wiki",
            "knowledge_base_type": "file_wiki",
            "input": {"query": "请根据售后政策文件生成 File Wiki，说明退货和人工审核规则。"},
            "expected": {
                "routes": ["file_wiki"],
                "evidence_ids": ["file:after-sale-policy"],
                "required_structured_fields": ["summary", "effective_rules", "source_evidence_ids"],
            },
        }
    )

    trace = ReferencePipeline("reference-v2").execute(case)

    assert trace.route.selected == ["file_wiki"]
    assert trace.generation.structured_output["source_evidence_ids"] == ["file:after-sale-policy"]


def test_v1_file_wiki_uses_unverifiable_citation():
    case = EvalCase.model_validate(
        {
            "case_id": "wiki-file",
            "task_type": "file_wiki",
            "metric_profile": "file_wiki",
            "input": {"query": "请根据售后政策文件生成 File Wiki，说明退货和人工审核规则。"},
            "expected": {"routes": ["file_wiki"]},
        }
    )

    trace = ReferencePipeline("reference-v1").execute(case)

    assert "file:missing-policy" in trace.generation.citations
