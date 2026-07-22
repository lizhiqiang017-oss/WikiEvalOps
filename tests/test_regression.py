from copy import deepcopy

import pytest

from wikievalops.contracts import RunArtifact
from wikievalops.errors import ConfigurationError
from wikievalops.regression import RegressionComparator


def _artifact(version, failed, route_score, risk_score, dataset="same"):
    return RunArtifact.model_validate(
        {
            "metadata": {
                "run_id": version,
                "system_version": version,
                "dataset_path": "cases.jsonl",
                "dataset_sha256": dataset,
                "config_sha256": "config",
                "case_count": 2,
            },
            "summary": {
                "core_metrics": {
                    "route_macro_f1": {"score": route_score},
                    "high_risk_recall": {"score": risk_score},
                },
                "metrics": {},
                "failed_case_ids": failed,
                "failure_category_counts": {"route_mismatch": len(failed)},
            },
            "cases": [],
        }
    )


def test_comparator_reports_improvement_and_fixed_cases():
    report = RegressionComparator().compare(
        _artifact("v1", ["a", "b"], 0.7, 0.5),
        _artifact("v2", [], 0.9, 1.0),
    )

    assert report.verdict == "improved"
    assert report.fixed_case_ids == ["a", "b"]
    assert report.core_metric_deltas["high_risk_recall"].delta == 0.5


def test_comparator_rejects_different_benchmarks():
    with pytest.raises(ConfigurationError, match="不同的 Benchmark"):
        RegressionComparator().compare(
            _artifact("v1", [], 1, 1, dataset="old"),
            _artifact("v2", [], 1, 1, dataset="new"),
        )
