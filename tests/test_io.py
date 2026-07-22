from __future__ import annotations

import pytest

from wikievalops.errors import DatasetValidationError
from wikievalops.io import load_cases, load_manifest, load_traces


def test_smoke_data_is_valid(project_root):
    cases = load_cases(project_root / "benchmarks/smoke/cases.jsonl")
    traces = load_traces(project_root / "examples/traces/reference-v1.jsonl")

    assert len(cases) == 15
    assert set(traces) == {case.case_id for case in cases}


def test_duplicate_case_ids_are_rejected(tmp_path):
    path = tmp_path / "cases.jsonl"
    line = '{"case_id":"duplicate","task_type":"routing","metric_profile":"routing","input":{"query":"q"},"expected":{}}\n'
    path.write_text(line + line, encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="case_id 重复"):
        load_cases(path)


def test_manifest_is_valid(project_root):
    manifest = load_manifest(project_root / "benchmarks/smoke/manifest.json")

    assert manifest.benchmark_id == "smoke-v1"
    assert manifest.dataset_path == "benchmarks/smoke/cases.jsonl"
    assert {source.source_id for source in manifest.evidence_sources} >= {
        "public-demo-repo",
        "synthetic-commerce-data",
        "售后政策.pdf",
    }


def test_duplicate_manifest_source_ids_are_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        """
{
  "benchmark_id": "bad",
  "dataset_path": "benchmarks/smoke/cases.jsonl",
  "description": "重复来源示例",
  "frozen_core_policy": "示例策略",
  "evidence_sources": [
    {
      "source_id": "same",
      "source_type": "document",
      "version": "v1",
      "description": "来源 A",
      "allowed_location_kinds": ["page"]
    },
    {
      "source_id": "same",
      "source_type": "document",
      "version": "v1",
      "description": "来源 B",
      "allowed_location_kinds": ["paragraph"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="source_id 不能重复"):
        load_manifest(path)
