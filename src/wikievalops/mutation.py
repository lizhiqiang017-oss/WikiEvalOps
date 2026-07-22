from __future__ import annotations

from collections import Counter
from pathlib import Path

from .contracts import ChallengeSetReport, DatasetSplit, EvalCase, MutationRecord
from .io import sha256_file, write_json, write_jsonl


class ChallengeSetBuilder:
    """把稳定样本变成更难的挑战样本，用于 mutation testing 和回归集扩展。"""

    def build(
        self,
        cases: list[EvalCase],
        source_dataset_path: Path,
        output_dataset_path: Path,
        report_path: Path,
    ) -> ChallengeSetReport:
        mutated_cases: list[EvalCase] = []
        records: list[MutationRecord] = []

        for case in cases:
            if case.dataset_split == DatasetSplit.HOLDOUT:
                continue
            mutated_case, record = self._mutate_case(case)
            mutated_cases.append(mutated_case)
            records.append(record)

        write_jsonl(output_dataset_path, mutated_cases)
        output_dataset_sha256 = sha256_file(output_dataset_path)
        report = ChallengeSetReport(
            source_dataset_path=str(source_dataset_path.resolve()),
            source_dataset_sha256=sha256_file(source_dataset_path),
            output_dataset_path=str(output_dataset_path.resolve()),
            output_dataset_sha256=output_dataset_sha256,
            source_case_count=len(cases),
            challenge_case_count=len(mutated_cases),
            skipped_case_count=len(cases) - len(mutated_cases),
            mutation_type_counts=dict(Counter(record.mutation_type for record in records)),
            split_counts=dict(Counter(str(case.dataset_split) for case in mutated_cases)),
            records=records,
        )
        write_json(report_path, report)
        return report

    def _mutate_case(self, case: EvalCase) -> tuple[EvalCase, MutationRecord]:
        query, mutation_type, rationale = self._mutate_query(case)
        payload = case.model_dump(mode="json")
        payload["case_id"] = f"challenge-{case.case_id}"
        payload["dataset_split"] = DatasetSplit.CHALLENGE.value
        payload["tags"] = sorted({*payload.get("tags", []), f"mutation:{mutation_type}", "challenge"})
        payload["input"]["query"] = query
        mutated_case = EvalCase.model_validate(payload)
        return (
            mutated_case,
            MutationRecord(
                source_case_id=case.case_id,
                mutated_case_id=mutated_case.case_id,
                mutation_type=mutation_type,
                dataset_split=mutated_case.dataset_split,
                knowledge_base_type=mutated_case.knowledge_base_type,
                rationale=rationale,
            ),
        )

    @staticmethod
    def _mutate_query(case: EvalCase) -> tuple[str, str, str]:
        base = case.input.query.rstrip("。")
        if case.task_type == "commerce_risk":
            return (
                f"{base}，同时说明相关接口来自哪个模块。",
                "technical_distractor",
                "在业务风险判断中加入技术链路干扰，模拟真实问答里跨域追问导致的路由压力。",
            )
        if case.task_type == "fact_wiki":
            return (
                f"{base}，并补充它与售后政策的关系。",
                "cross_domain_distractor",
                "让事实抽取问题同时出现文件政策干扰，测试事实库路由的纯度。",
            )
        if case.task_type == "file_wiki":
            return (
                f"{base}，顺带说明它和工单系统的处理链路有什么区别。",
                "workflow_distractor",
                "把文件 Wiki 和系统 Wiki 语义混在一起，测试结构化文件归因能力。",
            )
        if case.task_type == "system_wiki":
            return (
                f"{base}，也请说明它是否会影响服务商风险判断。",
                "business_distractor",
                "把系统链路问题和业务风险判断混在一起，测试多意图路由和结构输出。",
            )
        if case.task_type == "technical_qa":
            return (
                f"{base}，如果有必要也请补充售后政策里的相关规则。",
                "policy_distractor",
                "在技术问答中加入文件政策干扰，测试引用定位和路由稳定性。",
            )
        return (
            f"{base}，同时补充一个无关的业务说明。",
            "generic_distractor",
            "保留原任务主线的同时增加无关干扰，作为基础挑战样本。",
        )
