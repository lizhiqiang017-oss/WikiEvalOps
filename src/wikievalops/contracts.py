from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvalInput(StrictModel):
    query: str = Field(min_length=1)
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    business_data: dict[str, Any] = Field(default_factory=dict)


class ExpectedResult(StrictModel):
    routes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    risk_label: str | None = None


class EvalCase(StrictModel):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    task_type: str = Field(min_length=1)
    metric_profile: str = Field(min_length=1)
    risk_level: RiskLevel = RiskLevel.LOW
    tags: list[str] = Field(default_factory=list)
    input: EvalInput
    expected: ExpectedResult

    @model_validator(mode="after")
    def validate_expectations(self) -> "EvalCase":
        if self.metric_profile == "commerce_risk" and self.expected.risk_label is None:
            raise ValueError("commerce_risk cases require expected.risk_label")
        return self


class RouteTrace(StrictModel):
    selected: list[str] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RetrievedDocument(StrictModel):
    document_id: str = Field(min_length=1)
    score: float | None = None
    source: str | None = None
    content: str = ""


class RetrievalTrace(StrictModel):
    documents: list[RetrievedDocument] = Field(default_factory=list)


class ContextItem(StrictModel):
    evidence_id: str = Field(min_length=1)
    content: str = ""


class ContextTrace(StrictModel):
    items: list[ContextItem] = Field(default_factory=list)
    token_count: int | None = Field(default=None, ge=0)


class MemoryTrace(StrictModel):
    read_items: list[str] = Field(default_factory=list)
    written_items: list[str] = Field(default_factory=list)


class ClaimTrace(StrictModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class GenerationTrace(StrictModel):
    answer: str = ""
    claims: list[ClaimTrace] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    structured_output: dict[str, Any] = Field(default_factory=dict)
    risk_label: str | None = None


class EvaluationTrace(StrictModel):
    case_id: str
    system_version: str = Field(min_length=1)
    route: RouteTrace = Field(default_factory=RouteTrace)
    retrieval: RetrievalTrace = Field(default_factory=RetrievalTrace)
    context: ContextTrace = Field(default_factory=ContextTrace)
    memory: MemoryTrace = Field(default_factory=MemoryTrace)
    generation: GenerationTrace = Field(default_factory=GenerationTrace)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    cost: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class MetricResult(StrictModel):
    metric: str
    score: float = Field(ge=0, le=1)
    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CaseResult(StrictModel):
    case_id: str
    task_type: str
    risk_level: RiskLevel
    metric_results: list[MetricResult]
    trace_status: Literal["ok", "missing", "invalid"] = "ok"
    errors: list[str] = Field(default_factory=list)


class RunMetadata(StrictModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    system_version: str
    dataset_path: str
    dataset_sha256: str
    config_sha256: str
    case_count: int = Field(ge=0)


class RunArtifact(StrictModel):
    schema_version: str = "1.0"
    metadata: RunMetadata
    summary: dict[str, Any]
    cases: list[CaseResult]

