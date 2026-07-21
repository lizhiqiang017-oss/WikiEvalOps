from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, ValidationError

from .contracts import EvalCase, EvaluationTrace
from .errors import DatasetValidationError, TraceValidationError

T = TypeVar("T", bound=BaseModel)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path, model_type: type[T], error_type: type[Exception]) -> list[T]:
    if not path.is_file():
        raise error_type(f"file does not exist: {path}")
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
                raise error_type(f"{path}:{line_number}: duplicate case_id {row_id!r}")
            seen_ids.add(row_id)
            rows.append(row)
    if not rows:
        raise error_type(f"file contains no records: {path}")
    return rows


def load_cases(path: Path) -> list[EvalCase]:
    return _load_jsonl(path, EvalCase, DatasetValidationError)


def load_traces(path: Path) -> dict[str, EvaluationTrace]:
    traces = _load_jsonl(path, EvaluationTrace, TraceValidationError)
    return {trace.case_id: trace for trace in traces}


def write_json(path: Path, value: BaseModel | dict) -> None:
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

