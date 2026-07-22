from __future__ import annotations

from .contracts import MetricDelta, RegressionReport, RunArtifact
from .errors import ConfigurationError


class RegressionComparator:
    """比较同一数据集、同一评测配置下的两个系统版本。"""

    def compare(self, baseline: RunArtifact, candidate: RunArtifact) -> RegressionReport:
        if baseline.metadata.dataset_sha256 != candidate.metadata.dataset_sha256:
            raise ConfigurationError("Baseline 与 Candidate 使用了不同的 Benchmark，不能直接比较。")
        if baseline.metadata.config_sha256 != candidate.metadata.config_sha256:
            raise ConfigurationError("Baseline 与 Candidate 使用了不同的评测配置，不能直接比较。")

        core_deltas = self._metric_deltas(
            baseline.summary.get("core_metrics", {}),
            candidate.summary.get("core_metrics", {}),
            value_key="score",
        )
        metric_deltas = self._metric_deltas(
            baseline.summary.get("metrics", {}),
            candidate.summary.get("metrics", {}),
            value_key="mean",
        )
        baseline_failed = set(baseline.summary.get("failed_case_ids", []))
        candidate_failed = set(candidate.summary.get("failed_case_ids", []))
        failure_category_deltas = self._count_deltas(
            baseline.summary.get("failure_category_counts", {}),
            candidate.summary.get("failure_category_counts", {}),
        )

        return RegressionReport(
            baseline_version=baseline.metadata.system_version,
            candidate_version=candidate.metadata.system_version,
            dataset_sha256=baseline.metadata.dataset_sha256,
            verdict=self._verdict(core_deltas, baseline_failed, candidate_failed),
            core_metric_deltas=core_deltas,
            metric_deltas=metric_deltas,
            fixed_case_ids=sorted(baseline_failed - candidate_failed),
            regressed_case_ids=sorted(candidate_failed - baseline_failed),
            unchanged_failed_case_ids=sorted(baseline_failed & candidate_failed),
            failure_category_deltas=failure_category_deltas,
        )

    @staticmethod
    def _metric_deltas(baseline: dict, candidate: dict, value_key: str) -> dict[str, MetricDelta]:
        output = {}
        for name in sorted(set(baseline) & set(candidate)):
            before = float(baseline[name][value_key])
            after = float(candidate[name][value_key])
            output[name] = MetricDelta(baseline=before, candidate=after, delta=after - before)
        return output

    @staticmethod
    def _count_deltas(baseline: dict, candidate: dict) -> dict[str, int]:
        return {
            name: int(candidate.get(name, 0)) - int(baseline.get(name, 0))
            for name in sorted(set(baseline) | set(candidate))
        }

    @staticmethod
    def _verdict(
        core_deltas: dict[str, MetricDelta],
        baseline_failed: set[str],
        candidate_failed: set[str],
    ) -> str:
        values = [delta.delta for delta in core_deltas.values()]
        has_improvement = any(value > 1e-12 for value in values) or len(candidate_failed) < len(baseline_failed)
        has_regression = any(value < -1e-12 for value in values) or bool(candidate_failed - baseline_failed)
        if has_improvement and has_regression:
            return "mixed"
        if has_regression:
            return "regressed"
        if has_improvement:
            return "improved"
        return "unchanged"
