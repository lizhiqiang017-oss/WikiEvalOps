from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ConfigurationError


class EvaluationConfig(BaseModel):
    """评测配置：任务到指标的映射、阈值及缺失 Trace 策略。"""

    model_config = ConfigDict(extra="forbid")

    metric_profiles: dict[str, list[str]]
    metric_thresholds: dict[str, float] = Field(default_factory=dict)
    fail_on_missing_trace: bool = True


def load_config(path: Path) -> EvaluationConfig:
    """读取并严格校验 JSON 配置。"""

    if not path.is_file():
        raise ConfigurationError(f"配置文件不存在：{path}")
    try:
        return EvaluationConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"配置文件无效 {path}：{exc}") from exc
