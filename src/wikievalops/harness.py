from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from uuid import uuid4

from .adapters import SystemAdapter
from .attribution import AttributionEngine
from .config import EvaluationConfig
from .contracts import CaseResult, EvalCase, EvaluationTrace, RunArtifact, RunMetadata
from .errors import ConfigurationError
from .io import sha256_file, sha256_json, write_json, write_jsonl
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
        trace_output_path: Path | None = None,
    ) -> RunArtifact:
        """执行一次完整评测，并可将原始 Trace 单独落盘用于离线复算。"""

        case_results: list[CaseResult] = []
        recorded_traces: list[EvaluationTrace] = []
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
            recorded_traces.append(trace)
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
        summary = self._summarize(case_results, recorded_traces)
        quality_gate = self._evaluate_quality_gates(summary)
        summary["quality_gate"] = quality_gate
        summary["status"] = quality_gate["status"]
        trace_path = None
        trace_sha256 = None
        if trace_output_path is not None:
            write_jsonl(trace_output_path, recorded_traces)
            trace_path = str(trace_output_path.resolve())
            trace_sha256 = sha256_file(trace_output_path)
        artifact = RunArtifact(
            metadata=RunMetadata(
                run_id=self._new_run_id(),
                system_version=system_version,
                dataset_path=str(dataset_path.resolve()),
                dataset_sha256=sha256_file(dataset_path),
                config_sha256=sha256_json(self.config.model_dump(mode="json")),
                case_count=len(cases),
                trace_path=trace_path,
                trace_sha256=trace_sha256,
            ),
            summary=summary,
            cases=case_results,
        )
        write_json(output_path, artifact)
        return artifact

    @staticmethod
    def _new_run_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"

    def _summarize(self, results: list[CaseResult], traces: list[EvaluationTrace]) -> dict:
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
            "metrics": metrics,
            "core_metrics": core_metrics,
            "task_slices": slices,
            "failed_case_ids": sorted(set(failed_cases)),
            "failure_category_counts": dict(sorted(failure_category_counts.items())),
            "missing_or_invalid_trace_count": missing_traces,
            "threshold_failed_case_count": threshold_failed_cases,
            "efficiency": self._efficiency_summary(traces),
        }

    def _evaluate_quality_gates(self, summary: dict) -> dict:
        """用聚合指标生成 PASS/WARN/BLOCK，避免单一总分掩盖关键风险。"""

        checks = []
        for metric_name, rule in sorted(self.config.quality_gates.items()):
            metric_value = summary["core_metrics"].get(metric_name)
            score_key = "score"
            if metric_value is None:
                metric_value = summary["metrics"].get(metric_name)
                score_key = "mean"
            if metric_value is None:
                status = "BLOCK" if rule.required else "WARN"
                checks.append(
                    {
                        "metric": metric_name,
                        "score": None,
                        "status": status,
                        "reason": "运行结果中缺少必需聚合指标" if rule.required else "运行结果中缺少可选聚合指标",
                    }
                )
                continue

            score = float(metric_value[score_key])
            status = "BLOCK" if score < rule.block_below else "WARN" if score < rule.warn_below else "PASS"
            checks.append(
                {
                    "metric": metric_name,
                    "score": score,
                    "status": status,
                    "warn_below": rule.warn_below,
                    "block_below": rule.block_below,
                }
            )

        missing_count = int(summary["missing_or_invalid_trace_count"])
        if self.config.fail_on_missing_trace and missing_count:
            checks.append(
                {
                    "metric": "trace_integrity",
                    "score": None,
                    "status": "BLOCK",
                    "reason": f"存在 {missing_count} 条缺失或无效 Trace",
                }
            )

        # 兼容尚未迁移 quality_gates 的旧配置，避免升级后静默放过逐样本失败。
        if not self.config.quality_gates and summary["threshold_failed_case_count"]:
            checks.append(
                {
                    "metric": "case_metric_thresholds",
                    "score": None,
                    "status": "BLOCK",
                    "reason": f"存在 {summary['threshold_failed_case_count']} 条样本未通过指标阈值",
                }
            )

        statuses = {check["status"] for check in checks}
        overall = "BLOCK" if "BLOCK" in statuses else "WARN" if "WARN" in statuses else "PASS"
        return {"status": overall, "checks": checks}

    @classmethod
    def _efficiency_summary(cls, traces: list[EvaluationTrace]) -> dict:
        """汇总真实 Trace 中的延迟、成本和调用次数；缺失字段不做估算。"""

        latencies = [float(trace.timing_ms["total"]) for trace in traces if "total" in trace.timing_ms]
        usage_fields = ("tool_call_count", "retrieval_call_count", "retry_count")
        usage = {
            field: {
                "total": sum(getattr(trace.usage, field) for trace in traces),
                "mean": sum(getattr(trace.usage, field) for trace in traces) / len(traces) if traces else 0.0,
            }
            for field in usage_fields
        }
        cost_values: dict[str, list[float]] = defaultdict(list)
        for trace in traces:
            for name, value in trace.cost.items():
                cost_values[name].append(float(value))
        costs = {
            name: {"total": sum(values), "mean": sum(values) / len(values), "count": len(values)}
            for name, values in sorted(cost_values.items())
        }
        return {
            "evaluated_trace_count": len(traces),
            "latency_ms": cls._distribution(latencies),
            "usage": usage,
            "cost": costs,
        }

    @staticmethod
    def _distribution(values: list[float]) -> dict:
        if not values:
            return {"count": 0, "mean": None, "p50": None, "p95": None}
        ordered = sorted(values)

        def percentile(ratio: float) -> float:
            # 使用 nearest-rank，样本较少时也能给出稳定、易解释的结果。
            return ordered[max(0, ceil(ratio * len(ordered)) - 1)]

        return {
            "count": len(ordered),
            "mean": sum(ordered) / len(ordered),
            "p50": percentile(0.50),
            "p95": percentile(0.95),
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
