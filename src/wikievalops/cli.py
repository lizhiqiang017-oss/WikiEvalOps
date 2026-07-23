from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import OfflineTraceAdapter, ReferencePipelineAdapter
from .config import load_config
from .errors import WikiEvalError
from .evolution import EvalEvolutionPlanner
from .harness import EvaluationHarness
from .mutation import ChallengeSetBuilder
from .io import load_artifact, load_challenge_report, load_cases, load_manifest, load_regression_report, load_traces, write_json
from .reporting import MarkdownReporter
from .regression import RegressionComparator


def _parser() -> argparse.ArgumentParser:
    """创建中文命令行界面，命令和参数名保留稳定的英文 API。"""

    parser = argparse.ArgumentParser(prog="wikieval", description="评测企业知识系统的标准化执行 Trace。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="校验 JSONL Benchmark、Trace 或 Manifest 文件。")
    validate.add_argument("path", type=Path, help="待校验文件路径。")
    validate.add_argument("--kind", choices=("cases", "traces", "manifest"), default="cases", help="文件类型。")

    run = subparsers.add_parser("run", help="使用离线 Trace 执行 Benchmark。")
    run.add_argument("--dataset", type=Path, required=True, help="Benchmark JSONL 路径。")
    run.add_argument("--traces", type=Path, required=True, help="离线 Trace JSONL 路径。")
    run.add_argument("--config", type=Path, required=True, help="评测配置路径。")
    run.add_argument("--output", type=Path, required=True, help="运行产物输出路径。")
    run.add_argument("--trace-output", type=Path, help="可选：将本次标准 Trace 写入 JSONL。")

    reference = subparsers.add_parser("run-reference", help="运行内置 ReferencePipeline。")
    reference.add_argument("--dataset", type=Path, required=True, help="Benchmark JSONL 路径。")
    reference.add_argument("--config", type=Path, required=True, help="评测配置路径。")
    reference.add_argument("--version", choices=("reference-v1", "reference-v2"), required=True)
    reference.add_argument("--output", type=Path, required=True, help="运行产物输出路径。")
    reference.add_argument("--trace-output", type=Path, help="可选：将本次标准 Trace 写入 JSONL。")

    compare = subparsers.add_parser("compare", help="比较 Baseline 与 Candidate Artifact。")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)

    mutate = subparsers.add_parser("mutate", help="生成挑战集和 mutation 报告。")
    mutate.add_argument("--dataset", type=Path, required=True, help="Benchmark JSONL 路径。")
    mutate.add_argument("--output", type=Path, required=True, help="挑战集 JSONL 输出路径。")
    mutate.add_argument("--report", type=Path, required=True, help="mutation 报告输出路径。")

    evolve = subparsers.add_parser("evolve", help="根据失败归因生成 Eval 自进化候选建议。")
    evolve.add_argument("--artifact", type=Path, required=True, help="评测运行 Artifact 路径。")
    evolve.add_argument("--output", type=Path, required=True, help="Evolution 建议报告输出路径。")

    report = subparsers.add_parser("report", help="把运行产物或挑战集报告导出为 Markdown。")
    report.add_argument("--input", type=Path, required=True, help="输入 JSON 报告文件。")
    report.add_argument("--kind", choices=("run", "challenge", "regression"), required=True, help="输入类型。")
    report.add_argument("--output", type=Path, required=True, help="Markdown 输出路径。")
    return parser


def _validate(args: argparse.Namespace) -> int:
    if args.kind == "cases":
        records = load_cases(args.path)
        payload = {"status": "valid", "kind": args.kind, "record_count": len(records)}
    elif args.kind == "traces":
        records = load_traces(args.path)
        payload = {"status": "valid", "kind": args.kind, "record_count": len(records)}
    else:
        manifest = load_manifest(args.path)
        payload = {
            "status": "valid",
            "kind": args.kind,
            "benchmark_id": manifest.benchmark_id,
            "source_count": len(manifest.evidence_sources),
        }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _run(args: argparse.Namespace) -> int:
    cases = load_cases(args.dataset)
    traces = load_traces(args.traces)
    config = load_config(args.config)
    artifact = EvaluationHarness(config).run(
        cases=cases,
        adapter=OfflineTraceAdapter(traces),
        dataset_path=args.dataset,
        output_path=args.output,
        trace_output_path=args.trace_output,
    )
    print(
        json.dumps(
            {
                "status": artifact.summary["status"],
                "run_id": artifact.metadata.run_id,
                "system_version": artifact.metadata.system_version,
                "artifact": str(args.output.resolve()),
                "core_metrics": artifact.summary["core_metrics"],
            },
            ensure_ascii=False,
        )
    )
    return 2 if artifact.summary["status"] == "BLOCK" else 0


def _run_reference(args: argparse.Namespace) -> int:
    cases = load_cases(args.dataset)
    config = load_config(args.config)
    artifact = EvaluationHarness(config).run(
        cases=cases,
        adapter=ReferencePipelineAdapter(args.version),
        dataset_path=args.dataset,
        output_path=args.output,
        trace_output_path=args.trace_output,
    )
    print(
        json.dumps(
            {
                "status": artifact.summary["status"],
                "system_version": artifact.metadata.system_version,
                "artifact": str(args.output.resolve()),
                "core_metrics": artifact.summary["core_metrics"],
                "failure_categories": artifact.summary["failure_category_counts"],
                "quality_gate": artifact.summary["quality_gate"],
                "trace_output": str(args.trace_output.resolve()) if args.trace_output else None,
            },
            ensure_ascii=False,
        )
    )
    return 2 if artifact.summary["status"] == "BLOCK" else 0


def _compare(args: argparse.Namespace) -> int:
    report = RegressionComparator().compare(load_artifact(args.baseline), load_artifact(args.candidate))
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "verdict": report.verdict,
                "baseline": report.baseline_version,
                "candidate": report.candidate_version,
                "fixed_cases": report.fixed_case_ids,
                "regressed_cases": report.regressed_case_ids,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 3 if report.verdict in {"regressed", "mixed"} else 0


def _mutate(args: argparse.Namespace) -> int:
    cases = load_cases(args.dataset)
    report = ChallengeSetBuilder().build(
        cases=cases,
        source_dataset_path=args.dataset,
        output_dataset_path=args.output,
        report_path=args.report,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "source_case_count": report.source_case_count,
                "challenge_case_count": report.challenge_case_count,
                "mutation_type_counts": report.mutation_type_counts,
                "output": str(args.output.resolve()),
                "report": str(args.report.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _evolve(args: argparse.Namespace) -> int:
    report = EvalEvolutionPlanner().plan(load_artifact(args.artifact))
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report.status,
                "source_run_id": report.source_run_id,
                "failure_pattern_count": report.failure_pattern_count,
                "candidate_count": report.candidate_count,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _report(args: argparse.Namespace) -> int:
    reporter = MarkdownReporter()
    if args.kind == "run":
        report = reporter.render_run(load_artifact(args.input))
    elif args.kind == "challenge":
        report = reporter.render_challenge(load_challenge_report(args.input))
    else:
        report = reporter.render_regression(load_regression_report(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.content + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "kind": args.kind, "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args)
        if args.command == "run":
            return _run(args)
        if args.command == "run-reference":
            return _run_reference(args)
        if args.command == "mutate":
            return _mutate(args)
        if args.command == "evolve":
            return _evolve(args)
        if args.command == "report":
            return _report(args)
        return _compare(args)
    except WikiEvalError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
