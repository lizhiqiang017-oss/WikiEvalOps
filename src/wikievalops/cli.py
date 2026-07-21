from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import OfflineTraceAdapter
from .config import load_config
from .errors import WikiEvalError
from .harness import EvaluationHarness
from .io import load_cases, load_traces


def _parser() -> argparse.ArgumentParser:
    """创建中文命令行界面，命令和参数名保留稳定的英文 API。"""

    parser = argparse.ArgumentParser(prog="wikieval", description="评测企业知识系统的标准化执行 Trace。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="校验 JSONL Benchmark 或 Trace 文件。")
    validate.add_argument("path", type=Path, help="待校验文件路径。")
    validate.add_argument("--kind", choices=("cases", "traces"), default="cases", help="文件类型。")

    run = subparsers.add_parser("run", help="使用离线 Trace 执行 Benchmark。")
    run.add_argument("--dataset", type=Path, required=True, help="Benchmark JSONL 路径。")
    run.add_argument("--traces", type=Path, required=True, help="离线 Trace JSONL 路径。")
    run.add_argument("--config", type=Path, required=True, help="评测配置路径。")
    run.add_argument("--output", type=Path, required=True, help="运行产物输出路径。")
    return parser


def _validate(args: argparse.Namespace) -> int:
    records = load_cases(args.path) if args.kind == "cases" else load_traces(args.path)
    print(json.dumps({"status": "valid", "kind": args.kind, "record_count": len(records)}, ensure_ascii=False))
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
    return 0 if artifact.summary["status"] == "passed" else 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args)
        return _run(args)
    except WikiEvalError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
