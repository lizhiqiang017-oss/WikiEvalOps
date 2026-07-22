from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """所有外部数据都禁止未知字段，尽早暴露协议漂移。"""

    model_config = ConfigDict(extra="forbid")


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DatasetSplit(StrEnum):
    """样本分层用于区分稳定回归集、挑战集和只在最终验收使用的留出集。"""

    SMOKE = "smoke"
    FROZEN_CORE = "frozen_core"
    CHALLENGE = "challenge"
    HOLDOUT = "holdout"


class KnowledgeBaseType(StrEnum):
    """业务上常见的知识底座类型，便于后续按 Wiki 来源做切片分析。"""

    FACT_WIKI = "fact_wiki"
    FILE_WIKI = "file_wiki"
    SYSTEM_WIKI = "system_wiki"
    COMMERCE = "commerce"
    MIXED = "mixed"


class EvalInput(StrictModel):
    query: str = Field(min_length=1)
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    business_data: dict[str, Any] = Field(default_factory=dict)


class ExpectedResult(StrictModel):
    routes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_evidence_locations: dict[str, list[str]] = Field(default_factory=dict)
    required_claims: list[str] = Field(default_factory=list)
    risk_label: str | None = None
    required_structured_fields: list[str] = Field(default_factory=list)
    business_constraints: list[str] = Field(default_factory=list)


class EvalCase(StrictModel):
    """一条评测样本，描述输入、期望结果及应执行的指标配置。"""

    case_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    task_type: str = Field(min_length=1)
    metric_profile: str = Field(min_length=1)
    dataset_split: DatasetSplit = DatasetSplit.SMOKE
    knowledge_base_type: KnowledgeBaseType = KnowledgeBaseType.FACT_WIKI
    risk_level: RiskLevel = RiskLevel.LOW
    tags: list[str] = Field(default_factory=list)
    input: EvalInput
    expected: ExpectedResult

    @model_validator(mode="after")
    def validate_expectations(self) -> "EvalCase":
        """校验任务特有约束，避免运行阶段才发现 Gold Label 缺失。"""

        if self.metric_profile == "commerce_risk" and self.expected.risk_label is None:
            raise ValueError("commerce_risk 样本必须提供 expected.risk_label")
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
    locations: list["EvidenceLocation"] = Field(default_factory=list)


class RetrievalTrace(StrictModel):
    documents: list[RetrievedDocument] = Field(default_factory=list)


class ContextItem(StrictModel):
    evidence_id: str = Field(min_length=1)
    content: str = ""
    locations: list["EvidenceLocation"] = Field(default_factory=list)


class ContextTrace(StrictModel):
    items: list[ContextItem] = Field(default_factory=list)
    token_count: int | None = Field(default=None, ge=0)


class MemoryTrace(StrictModel):
    read_items: list[str] = Field(default_factory=list)
    written_items: list[str] = Field(default_factory=list)


class EvidenceLocation(StrictModel):
    """证据在原始来源中的可复验位置，如页码、段落、代码行或业务字段路径。"""

    kind: Literal["page", "paragraph", "line", "field_path"]
    value: str = Field(min_length=1)


class UsageTrace(StrictModel):
    """一次执行中可由被测系统直接观测的资源使用量。"""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    retrieval_call_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)


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
    """被测系统单次执行的标准 Trace，与具体 Agent/RAG 框架解耦。"""

    case_id: str
    system_version: str = Field(min_length=1)
    route: RouteTrace = Field(default_factory=RouteTrace)
    retrieval: RetrievalTrace = Field(default_factory=RetrievalTrace)
    context: ContextTrace = Field(default_factory=ContextTrace)
    memory: MemoryTrace = Field(default_factory=MemoryTrace)
    generation: GenerationTrace = Field(default_factory=GenerationTrace)
    usage: UsageTrace = Field(default_factory=UsageTrace)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    cost: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class MetricResult(StrictModel):
    metric: str
    score: float = Field(ge=0, le=1)
    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FailureAttribution(StrictModel):
    """阶段级错误归因，保留主因、次因、判断证据和修复建议。"""

    primary_failure: str | None = None
    secondary_failures: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class CaseResult(StrictModel):
    case_id: str
    task_type: str
    dataset_split: DatasetSplit = DatasetSplit.SMOKE
    knowledge_base_type: KnowledgeBaseType = KnowledgeBaseType.FACT_WIKI
    risk_level: RiskLevel
    metric_results: list[MetricResult]
    trace_status: Literal["ok", "missing", "invalid"] = "ok"
    errors: list[str] = Field(default_factory=list)
    attribution: FailureAttribution = Field(default_factory=FailureAttribution)


class RunMetadata(StrictModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    system_version: str
    dataset_path: str
    dataset_sha256: str
    config_sha256: str
    case_count: int = Field(ge=0)
    trace_path: str | None = None
    trace_sha256: str | None = None


class RunArtifact(StrictModel):
    """一次评测运行的可复现产物，包含元数据、汇总和逐样本结果。"""

    schema_version: str = "1.2"
    metadata: RunMetadata
    summary: dict[str, Any]
    cases: list[CaseResult]


class MutationRecord(StrictModel):
    """记录一条挑战样本是从哪个样本、通过什么方式变异而来。"""

    source_case_id: str
    mutated_case_id: str
    mutation_type: str
    dataset_split: DatasetSplit
    knowledge_base_type: KnowledgeBaseType
    rationale: str


class ChallengeSetReport(StrictModel):
    """挑战集生成报告，便于回溯每条变异样本的来源和覆盖情况。"""

    schema_version: str = "1.0"
    source_dataset_path: str
    source_dataset_sha256: str
    output_dataset_path: str
    output_dataset_sha256: str
    source_case_count: int = Field(ge=0)
    challenge_case_count: int = Field(ge=0)
    skipped_case_count: int = Field(ge=0)
    mutation_type_counts: dict[str, int] = Field(default_factory=dict)
    split_counts: dict[str, int] = Field(default_factory=dict)
    records: list[MutationRecord] = Field(default_factory=list)


class EvidenceSourceSpec(StrictModel):
    """描述一类证据来源的治理规则，不存放真实生产数据。"""

    source_id: str = Field(min_length=1)
    source_type: Literal["code", "document", "system_design", "business_table"]
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    allowed_location_kinds: list[Literal["page", "paragraph", "line", "field_path"]]


class BenchmarkManifest(StrictModel):
    """Benchmark 的来源清单，用来说明样本、证据和冻结策略。"""

    schema_version: str = "1.0"
    benchmark_id: str = Field(min_length=1)
    dataset_path: str = Field(min_length=1)
    description: str = Field(min_length=1)
    frozen_core_policy: str = Field(min_length=1)
    evidence_sources: list[EvidenceSourceSpec]
    split_targets: dict[DatasetSplit, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manifest_governance(self) -> "BenchmarkManifest":
        """校验 Benchmark 治理规则，避免来源清单本身不可审计。"""

        source_ids = [source.source_id for source in self.evidence_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence_sources.source_id 不能重复")
        invalid_splits = [split.value for split, count in self.split_targets.items() if count < 0]
        if invalid_splits:
            raise ValueError(f"split_targets 不能为负数：{invalid_splits}")
        return self


class MarkdownReport(StrictModel):
    """导出的中文 Markdown 报表，便于面试展示和人工审阅。"""

    schema_version: str = "1.0"
    title: str
    content: str


class MetricDelta(StrictModel):
    """Baseline 与 Candidate 在一个指标上的差值。"""

    baseline: float
    candidate: float
    delta: float


class RegressionReport(StrictModel):
    """两个系统版本在同一 Benchmark 上的对比报告。"""

    schema_version: str = "1.0"
    baseline_version: str
    candidate_version: str
    dataset_sha256: str
    verdict: Literal["improved", "regressed", "mixed", "unchanged"]
    core_metric_deltas: dict[str, MetricDelta]
    metric_deltas: dict[str, MetricDelta]
    fixed_case_ids: list[str]
    regressed_case_ids: list[str]
    unchanged_failed_case_ids: list[str]
    failure_category_deltas: dict[str, int]
