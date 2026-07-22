from __future__ import annotations

from wikievalops.adapters import OfflineTraceAdapter
from wikievalops.adapters import ReferencePipelineAdapter
from wikievalops.config import QualityGateRule, load_config
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
    assert artifact.summary["status"] == "BLOCK"
    assert artifact.summary["quality_gate"]["status"] == "BLOCK"
    assert "risk-003" in artifact.summary["failed_case_ids"]
    assert "challenge" in artifact.summary["dataset_split_slices"]
    assert "file_wiki" in artifact.summary["knowledge_base_slices"]


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


def test_reference_trace_is_recorded_with_digest_and_efficiency(project_root, tmp_path):
    dataset = project_root / "benchmarks/smoke/cases.jsonl"
    trace_output = tmp_path / "reference-v2.jsonl"

    artifact = EvaluationHarness(load_config(project_root / "configs/evaluation.json")).run(
        load_cases(dataset),
        ReferencePipelineAdapter("reference-v2"),
        dataset,
        tmp_path / "artifact.json",
        trace_output_path=trace_output,
    )

    assert artifact.summary["status"] == "PASS"
    assert len(load_traces(trace_output)) == 15
    assert artifact.metadata.trace_path == str(trace_output.resolve())
    assert artifact.metadata.trace_sha256
    assert artifact.summary["efficiency"]["latency_ms"]["count"] == 15
    assert artifact.summary["efficiency"]["usage"]["retrieval_call_count"]["total"] == 15


def test_warning_gate_does_not_block_run(project_root, tmp_path):
    dataset = project_root / "benchmarks/smoke/cases.jsonl"
    config = load_config(project_root / "configs/evaluation.json")
    config.quality_gates = {
        "route_macro_f1": QualityGateRule(warn_below=0.99, block_below=0.70),
    }

    artifact = EvaluationHarness(config).run(
        load_cases(dataset),
        OfflineTraceAdapter(load_traces(project_root / "examples/traces/reference-v1.jsonl")),
        dataset,
        tmp_path / "artifact.json",
    )

    assert artifact.summary["status"] == "WARN"
