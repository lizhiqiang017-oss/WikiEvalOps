from __future__ import annotations

import pytest

from wikievalops.errors import DatasetValidationError
from wikievalops.io import load_cases, load_traces


def test_smoke_data_is_valid(project_root):
    cases = load_cases(project_root / "benchmarks/smoke/cases.jsonl")
    traces = load_traces(project_root / "examples/traces/reference-v1.jsonl")

    assert len(cases) == 12
    assert set(traces) == {case.case_id for case in cases}


def test_duplicate_case_ids_are_rejected(tmp_path):
    path = tmp_path / "cases.jsonl"
    line = '{"case_id":"duplicate","task_type":"routing","metric_profile":"routing","input":{"query":"q"},"expected":{}}\n'
    path.write_text(line + line, encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="duplicate case_id"):
        load_cases(path)
