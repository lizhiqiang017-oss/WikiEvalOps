from __future__ import annotations

from .contracts import ChallengeSetReport, MarkdownReport, RegressionReport, RunArtifact


class MarkdownReporter:
    """把运行产物和挑战集报告整理成适合阅读的中文 Markdown。"""

    def render_run(self, artifact: RunArtifact) -> MarkdownReport:
        summary = artifact.summary
        lines = [
            f"# 运行报告：{artifact.metadata.system_version}",
            "",
            f"- 运行 ID：{artifact.metadata.run_id}",
            f"- 状态：{summary['status']}",
            f"- 样本数：{artifact.metadata.case_count}",
            f"- 数据集：{artifact.metadata.dataset_path}",
            "",
            "## 核心指标",
        ]
        for name, value in sorted(summary.get("core_metrics", {}).items()):
            lines.append(f"- {name}：{value['score']:.4f}")

        lines.extend(
            [
                "",
                "## 门禁检查",
            ]
        )
        for check in summary.get("quality_gate", {}).get("checks", []):
            score = "N/A" if check.get("score") is None else f"{float(check['score']):.4f}"
            lines.append(f"- {check['metric']}：{check['status']}（{score}）")

        self._append_slice_block(lines, "数据集分层切片", summary.get("dataset_split_slices", {}))
        self._append_slice_block(lines, "知识底座切片", summary.get("knowledge_base_slices", {}))

        failed = summary.get("failed_case_ids", [])
        lines.extend(["", "## 失败样本", ", ".join(failed) if failed else "- 无"])
        return MarkdownReport(title=f"运行报告：{artifact.metadata.system_version}", content="\n".join(lines))

    def render_challenge(self, report: ChallengeSetReport) -> MarkdownReport:
        lines = [
            "# 挑战集报告",
            "",
            f"- 源样本数：{report.source_case_count}",
            f"- 挑战样本数：{report.challenge_case_count}",
            f"- 跳过样本数：{report.skipped_case_count}",
            f"- 源数据集：{report.source_dataset_path}",
            f"- 输出数据集：{report.output_dataset_path}",
            "",
            "## 变异类型",
        ]
        for name, count in sorted(report.mutation_type_counts.items()):
            lines.append(f"- {name}：{count}")
        lines.extend(["", "## 分层分布"])
        for name, count in sorted(report.split_counts.items()):
            lines.append(f"- {name}：{count}")
        lines.append("")
        lines.append("## 变异记录")
        for record in report.records:
            lines.append(
                f"- {record.mutated_case_id} ← {record.source_case_id} | {record.mutation_type} | {record.rationale}"
            )
        return MarkdownReport(title="挑战集报告", content="\n".join(lines))

    def render_regression(self, report: RegressionReport) -> MarkdownReport:
        lines = [
            f"# 对比报告：{report.baseline_version} → {report.candidate_version}",
            "",
            f"- 结论：{report.verdict}",
            f"- 数据集 SHA-256：{report.dataset_sha256}",
            "",
            "## 核心指标变化",
        ]
        for name, delta in sorted(report.core_metric_deltas.items()):
            lines.append(f"- {name}：{delta.baseline:.4f} → {delta.candidate:.4f}（{delta.delta:+.4f}）")

        lines.append("")
        lines.append("## 常规指标变化")
        if report.metric_deltas:
            for name, delta in sorted(report.metric_deltas.items()):
                lines.append(f"- {name}：{delta.baseline:.4f} → {delta.candidate:.4f}（{delta.delta:+.4f}）")
        else:
            lines.append("- 无")

        lines.extend(
            [
                "",
                "## 样本变化",
                f"- 修复样本：{', '.join(report.fixed_case_ids) if report.fixed_case_ids else '无'}",
                f"- 退化样本：{', '.join(report.regressed_case_ids) if report.regressed_case_ids else '无'}",
                f"- 持续失败样本：{', '.join(report.unchanged_failed_case_ids) if report.unchanged_failed_case_ids else '无'}",
                "",
                "## 失败类别变化",
            ]
        )
        if report.failure_category_deltas:
            for name, delta in sorted(report.failure_category_deltas.items()):
                lines.append(f"- {name}：{delta:+d}")
        else:
            lines.append("- 无")

        return MarkdownReport(title=f"对比报告：{report.baseline_version} → {report.candidate_version}", content="\n".join(lines))

    @staticmethod
    def _append_slice_block(lines: list[str], title: str, slices: dict) -> None:
        lines.extend(["", f"## {title}"])
        if not slices:
            lines.append("- 无")
            return
        for slice_name, metrics in sorted(slices.items()):
            metric_parts = ", ".join(
                f"{metric}={stats['mean']:.4f}" for metric, stats in sorted(metrics.items())
            )
            lines.append(f"- {slice_name}：{metric_parts}")
