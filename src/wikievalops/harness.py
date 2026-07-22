from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .adapters import SystemAdapter
from .attribution import AttributionEngine
from .config import EvaluationConfig
from .contracts import CaseResult, EvalCase, RunArtifact, RunMetadata
from .errors import ConfigurationError
from .io import sha256_file, sha256_json, write_json
from .metrics import MetricRegistry


class EvaluationHarness:
    """评测主执行器：按样本选择指标、聚合结果并落盘 Artifact。"""

    def __init__(
        self,
        config: EvaluationConfig,
        registry: MetricRegistry | None = None,
        attribution_engine: AttributionEngine | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or MetricRegistry.default()
        self.attribution_engine = attribution_engine or AttributionEngine()

    def run(
        self,
        cases: list[EvalCase],
        adapter: SystemAdapter,
        dataset_path: Path,
        output_path: Path,
    ) -> RunArtifact:
        """执行一次完整评测；同一次运行只允许包含一个系统版本。"""

        case_results: list[CaseResult] = []
        system_versions: set[str] = set()

        for case in cases:
            metric_names = self.config.metric_profiles.get(case.metric_profile)
            if metric_names is None:
                raise ConfigurationError(f"未知指标配置：{case.metric_profile}")
            trace = adapter.execute(case)
            if trace is None:
                case_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        task_type=case.task_type,
                        risk_level=case.risk_level,
                        metric_results=[],
                        trace_status="missing",
                        errors=["未找到对应 Trace"],
                        attribution=self.attribution_engine.analyze(case, None, [], "missing"),
                    )
                )
                continue
            if trace.case_id != case.case_id:
                case_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        task_type=case.task_type,
                        risk_level=case.risk_level,
                        metric_results=[],
                        trace_status="invalid",
                        errors=[f"Trace case_id 不匹配：{trace.case_id}"],
                        attribution=self.attribution_engine.analyze(case, None, [], "invalid"),
                    )
                )
                continue

            system_versions.add(trace.system_version)
            metric_results = []
            for metric in self.registry.resolve(metric_names):
                result = metric.evaluate(case, trace)
                threshold = self.config.metric_thresholds.get(metric.name)
                result.passed = None if threshold is None else result.score >= threshold
                metric_results.append(result)
            case_results.append(
                CaseResult(
                    case_id=case.case_id,
                    task_type=case.task_type,
                    risk_level=case.risk_level,
                    metric_results=metric_results,
                    errors=list(trace.errors),
                    attribution=self.attribution_engine.analyze(case, trace, metric_results),
                )
            )

        if len(system_versions) > 1:
            raise ConfigurationError(f"一次运行不能混用多个系统版本：{sorted(system_versions)}")
        system_version = next(iter(system_versions), "unknown")
        artifact = RunArtifact(
            metadata=RunMetadata(
                run_id=self._new_run_id(),
                system_version=system_version,
                dataset_path=str(dataset_path.resolve()),
                dataset_sha256=sha256_file(dataset_path),
                config_sha256=sha256_json(self.config.model_dump(mode="json")),
                case_count=len(cases),
            ),
            summary=self._summarize(case_results),
            cases=case_results,
        )
        write_json(output_path, artifact)
        return artifact

    @staticmethod
    def _new_run_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"

    def _summarize(self, results: list[CaseResult]) -> dict:
        """汇总指标均值、任务切片和失败样本，供报告和 CI 使用。"""

        metric_scores: dict[str, list[float]] = defaultdict(list)
        task_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        failed_cases: list[str] = []
        missing_traces = 0
        threshold_failed_cases = 0
        failure_category_counts: dict[str, int] = defaultdict(int)

        for case_result in results:
            if case_result.trace_status != "ok":
                missing_traces += 1
                failed_cases.append(case_result.case_id)
                if case_result.attribution.primary_failure:
                    failure_category_counts[case_result.attribution.primary_failure] += 1
                continue
            if case_result.attribution.primary_failure:
                failure_category_counts[case_result.attribution.primary_failure] += 1
            case_failed = False
            for metric in case_result.metric_results:
                metric_scores[metric.metric].append(metric.score)
                task_scores[case_result.task_type][metric.metric].append(metric.score)
                if metric.passed is False:
                    case_failed = True
            if case_failed:
                failed_cases.append(case_result.case_id)
                threshold_failed_cases += 1

        metrics = {
            name: {"mean": sum(scores) / len(scores), "count": len(scores)}
            for name, scores in sorted(metric_scores.items())
        }
        slices = {
            task: {
                metric: {"mean": sum(scores) / len(scores), "count": len(scores)}
                for metric, scores in sorted(metric_map.items())
            }
            for task, metric_map in sorted(task_scores.items())
        }
        core_metrics = self._core_metrics(results)
        return {
            "status": "failed"
            if threshold_failed_cases or (self.config.fail_on_missing_trace and missing_traces)
            else "passed",
            "metrics": metrics,
            "core_metrics": core_metrics,
            "task_slices": slices,
            "failed_case_ids": sorted(set(failed_cases)),
            "failure_category_counts": dict(sorted(failure_category_counts.items())),
            "missing_or_invalid_trace_count": missing_traces,
        }

    @staticmethod
    def _core_metrics(results: list[CaseResult]) -> dict[str, dict[str, float | int]]:
        """计算必须跨样本统计的核心指标，避免用单样本均值冒充聚合指标。"""

        route_labels: set[str] = set()
        route_rows: list[tuple[set[str], set[str]]] = []
        high_risk_total = 0
        high_risk_detected = 0

        for case_result in results:
            if case_result.trace_status != "ok":
                continue
            for metric in case_result.metric_results:
                if metric.metric == "route_correctness":
                    expected = set(metric.details["expected"])
                    selected = set(metric.details["selected"])
                    route_labels.update(expected)
                    route_labels.update(selected)
                    route_rows.append((expected, selected))
                elif metric.metric == "risk_label_correctness" and metric.details.get("expected") == "high":
                    high_risk_total += 1
                    high_risk_detected += int(metric.details.get("actual") == "high")

        output: dict[str, dict[str, float | int]] = {}
        if route_labels:
            per_label_f1 = []
            for label in sorted(route_labels):
                # 逐路由类别计算 F1 后取宏平均，避免大类掩盖小类退化。
                true_positive = sum(label in expected and label in selected for expected, selected in route_rows)
                false_positive = sum(label not in expected and label in selected for expected, selected in route_rows)
                false_negative = sum(label in expected and label not in selected for expected, selected in route_rows)
                denominator = 2 * true_positive + false_positive + false_negative
                per_label_f1.append(0.0 if denominator == 0 else 2 * true_positive / denominator)
            output["route_macro_f1"] = {
                "score": sum(per_label_f1) / len(per_label_f1),
                "label_count": len(route_labels),
            }
        if high_risk_total:
            output["high_risk_recall"] = {
                "score": high_risk_detected / high_risk_total,
                "positive_case_count": high_risk_total,
            }
        return output
