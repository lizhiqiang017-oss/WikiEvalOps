from __future__ import annotations

from wikievalops.adapters import OfflineTraceAdapter
from wikievalops.config import load_config
from wikievalops.harness import EvaluationHarness
from wikievalops.io import load_cases, load_traces


def test_end_to_end_artifact_contains_core_metrics(project_root, tmp_path):
    dataset = project_root / "benchmarks/smoke/cases.jsonl"
    cases = load_cases(dataset)
    traces = load_traces(project_root / "examples/traces/reference-v1.jsonl")
    config = load_config(project_root / "configs/evaluation.json")
    output = tmp_path / "artifact.json"

    artifact = EvaluationHarness(config).run(
        cases,
        OfflineTraceAdapter(traces),
        dataset,
        output,
    )

    assert output.is_file()
    assert artifact.metadata.system_version == "reference-v1"
    assert artifact.summary["core_metrics"]["route_macro_f1"]["score"] < 1
    assert artifact.summary["core_metrics"]["high_risk_recall"]["score"] == 2 / 3
    assert artifact.summary["core_metrics"]["high_risk_recall"]["positive_case_count"] == 3
    assert artifact.summary["status"] == "failed"
    assert "risk-003" in artifact.summary["failed_case_ids"]


def test_missing_trace_is_recorded(project_root, tmp_path):
    dataset = project_root / "benchmarks/smoke/cases.jsonl"
    cases = load_cases(dataset)
    traces = load_traces(project_root / "examples/traces/reference-v1.jsonl")
    traces.pop("qa-003")
    config = load_config(project_root / "configs/evaluation.json")

    artifact = EvaluationHarness(config).run(
        cases,
        OfflineTraceAdapter(traces),
        dataset,
        tmp_path / "artifact.json",
    )

    result = next(row for row in artifact.cases if row.case_id == "qa-003")
    assert result.trace_status == "missing"
    assert artifact.summary["missing_or_invalid_trace_count"] == 1
    assert artifact.summary["failure_category_counts"]["trace_missing"] == 1
