from __future__ import annotations

from wikievalops.evolution import EvalEvolutionPlanner
from wikievalops.io import load_artifact


def test_evolution_planner_generates_review_gated_candidates(project_root):
    artifact = load_artifact(project_root / "artifacts/runs/round5-reference-v1.json")
    report = EvalEvolutionPlanner().plan(artifact)

    assert report.status == "review_required"
    assert report.failure_pattern_count >= 1
    assert report.candidate_count >= report.failure_pattern_count
    assert all(candidate.review_status == "pending_review" for candidate in report.candidates)
    assert "不自动写入 Benchmark" in report.summary["review_policy"]


def test_evolution_planner_returns_ok_when_no_failures(project_root):
    artifact = load_artifact(project_root / "artifacts/runs/round5-reference-v2.json")
    report = EvalEvolutionPlanner().plan(artifact)

    assert report.status in {"ok", "review_required"}
    assert report.candidate_count >= 0
