from __future__ import annotations

from abc import ABC, abstractmethod

from .contracts import EvalCase, EvaluationTrace


class SystemAdapter(ABC):
    """将不同被测系统的输出统一转换为 EvaluationTrace。"""

    @abstractmethod
    def execute(self, case: EvalCase) -> EvaluationTrace | None:
        """执行一条样本并返回标准 Trace；无结果时返回 None。"""


class OfflineTraceAdapter(SystemAdapter):
    """直接读取已生成的 Trace，适合离线回放和可复现实验。"""

    def __init__(self, traces: dict[str, EvaluationTrace]) -> None:
        self._traces = traces

    def execute(self, case: EvalCase) -> EvaluationTrace | None:
        return self._traces.get(case.case_id)


class ReferencePipelineAdapter(SystemAdapter):
    """将可执行 ReferencePipeline 接入统一 EvaluationHarness。"""

    def __init__(self, version: str) -> None:
        # 延迟导入避免 Adapter 基础模块和演示系统形成初始化环依赖。
        from .reference_pipeline import ReferencePipeline

        self._pipeline = ReferencePipeline(version)

    def execute(self, case: EvalCase) -> EvaluationTrace:
        return self._pipeline.execute(case)
