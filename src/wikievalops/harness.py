from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .adapters import SystemAdapter
from .config import EvaluationConfig
from .contracts import CaseResult, EvalCase, RunArtifact, RunMetadata
from .errors import ConfigurationError
from .io import sha256_file, sha256_json, write_json
from .metrics import MetricRegistry


class EvaluationHarness:
    def __init__(
        self,
        config: EvaluationConfig,
        registry: MetricRegistry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or MetricRegistry.default()

    def run(
        self,
        cases: list[EvalCase],
        adapter: SystemAdapter,
        dataset_path: Path,
        output_path: Path,
    ) -> RunArtifact:
        case_results: list[CaseResult] = []
        system_versions: set[str] = set()

        for case in cases:
            metric_names = self.config.metric_profiles.get(case.metric_profile)
            if metric_names is None:
                raise ConfigurationError(f"unknown metric profile: {case.metric_profile}")
            trace = adapter.execute(case)
            if trace is None:
                case_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        task_type=case.task_type,
                        risk_level=case.risk_level,
                        metric_results=[],
                        trace_status="missing",
                        errors=["trace not found"],
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
                        errors=[f"trace case_id mismatch: {trace.case_id}"],
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
                )
            )

        if len(system_versions) > 1:
            raise ConfigurationError(f"one run cannot mix system versions: {sorted(system_versions)}")
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
        metric_scores: dict[str, list[float]] = defaultdict(list)
        task_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        failed_cases: list[str] = []
        missing_traces = 0

        for case_result in results:
            if case_result.trace_status != "ok":
                missing_traces += 1
                failed_cases.append(case_result.case_id)
                continue
            case_failed = False
            for metric in case_result.metric_results:
                metric_scores[metric.metric].append(metric.score)
                task_scores[case_result.task_type][metric.metric].append(metric.score)
                if metric.passed is False:
                    case_failed = True
            if case_failed:
                failed_cases.append(case_result.case_id)

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
            "status": "failed" if failed_cases or (self.config.fail_on_missing_trace and missing_traces) else "passed",
            "metrics": metrics,
            "core_metrics": core_metrics,
            "task_slices": slices,
            "failed_case_ids": sorted(set(failed_cases)),
            "missing_or_invalid_trace_count": missing_traces,
        }

    @staticmethod
    def _core_metrics(results: list[CaseResult]) -> dict[str, dict[str, float | int]]:
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
