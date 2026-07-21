from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ConfigurationError


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_profiles: dict[str, list[str]]
    metric_thresholds: dict[str, float] = Field(default_factory=dict)
    fail_on_missing_trace: bool = True


def load_config(path: Path) -> EvaluationConfig:
    if not path.is_file():
        raise ConfigurationError(f"configuration does not exist: {path}")
    try:
        return EvaluationConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"invalid configuration {path}: {exc}") from exc

