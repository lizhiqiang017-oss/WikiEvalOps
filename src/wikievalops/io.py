from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, ValidationError

from .contracts import (
    BenchmarkManifest,
    ChallengeSetReport,
    EvalCase,
    EvalEvolutionReport,
    EvaluationTrace,
    RegressionReport,
    RunArtifact,
)
from .errors import DatasetValidationError, TraceValidationError

T = TypeVar("T", bound=BaseModel)


def sha256_file(path: Path) -> str:
    """流式计算文件摘要，支持未来扩展到较大的 Benchmark。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path, model_type: type[T], error_type: type[Exception]) -> list[T]:
    """逐行校验 JSONL，并在错误中保留文件名和行号。"""

    if not path.is_file():
        raise error_type(f"文件不存在：{path}")
    rows: list[T] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = model_type.model_validate_json(line)
            except (ValidationError, ValueError) as exc:
                raise error_type(f"{path}:{line_number}: {exc}") from exc
            row_id = str(getattr(row, "case_id", ""))
            if row_id in seen_ids:
                raise error_type(f"{path}:{line_number}: case_id 重复：{row_id!r}")
            seen_ids.add(row_id)
            rows.append(row)
    if not rows:
        raise error_type(f"文件中没有有效记录：{path}")
    return rows


def load_cases(path: Path) -> list[EvalCase]:
    return _load_jsonl(path, EvalCase, DatasetValidationError)


def load_manifest(path: Path) -> BenchmarkManifest:
    """读取并校验 Benchmark 来源清单。"""

    if not path.is_file():
        raise DatasetValidationError(f"Manifest 不存在：{path}")
    try:
        return BenchmarkManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise DatasetValidationError(f"Manifest 无效 {path}：{exc}") from exc


def load_traces(path: Path) -> dict[str, EvaluationTrace]:
    traces = _load_jsonl(path, EvaluationTrace, TraceValidationError)
    return {trace.case_id: trace for trace in traces}


def load_artifact(path: Path) -> RunArtifact:
    """读取并校验评测 Artifact。"""

    if not path.is_file():
        raise TraceValidationError(f"Artifact 不存在：{path}")
    try:
        return RunArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise TraceValidationError(f"Artifact 无效 {path}：{exc}") from exc


def load_evolution_report(path: Path) -> EvalEvolutionReport:
    """读取并校验 Eval 自进化建议报告。"""

    if not path.is_file():
        raise TraceValidationError(f"Evolution 报告不存在：{path}")
    try:
        return EvalEvolutionReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise TraceValidationError(f"Evolution 报告无效 {path}：{exc}") from exc


def load_challenge_report(path: Path) -> ChallengeSetReport:
    """读取并校验 challenge/mutation 报告。"""

    if not path.is_file():
        raise TraceValidationError(f"Challenge 报告不存在：{path}")
    try:
        return ChallengeSetReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise TraceValidationError(f"Challenge 报告无效 {path}：{exc}") from exc


def load_regression_report(path: Path) -> RegressionReport:
    """读取并校验版本对比报告。"""

    if not path.is_file():
        raise TraceValidationError(f"Regression 报告不存在：{path}")
    try:
        return RegressionReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise TraceValidationError(f"Regression 报告无效 {path}：{exc}") from exc


def write_json(path: Path, value: BaseModel | dict) -> None:
    """先写临时文件再原子替换，避免留下半份运行产物。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, values: Iterable[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(value.model_dump_json() + "\n")
    temporary.replace(path)
