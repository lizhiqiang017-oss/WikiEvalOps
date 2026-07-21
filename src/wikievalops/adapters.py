from __future__ import annotations

from abc import ABC, abstractmethod

from .contracts import EvalCase, EvaluationTrace


class SystemAdapter(ABC):
    @abstractmethod
    def execute(self, case: EvalCase) -> EvaluationTrace | None:
        """Return a normalized trace for one evaluation case."""


class OfflineTraceAdapter(SystemAdapter):
    def __init__(self, traces: dict[str, EvaluationTrace]) -> None:
        self._traces = traces

    def execute(self, case: EvalCase) -> EvaluationTrace | None:
        return self._traces.get(case.case_id)

