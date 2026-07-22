from wikievalops.cli import main
from wikievalops.io import load_cases, load_traces


def test_validate_cli(project_root, capsys):
    exit_code = main(["validate", str(project_root / "benchmarks/smoke/cases.jsonl")])

    assert exit_code == 0
    assert '"record_count": 15' in capsys.readouterr().out


def test_run_cli_returns_two_when_thresholds_fail(project_root, tmp_path):
    exit_code = main(
        [
            "run",
            "--dataset",
            str(project_root / "benchmarks/smoke/cases.jsonl"),
            "--traces",
            str(project_root / "examples/traces/reference-v1.jsonl"),
            "--config",
            str(project_root / "configs/evaluation.json"),
            "--output",
            str(tmp_path / "artifact.json"),
        ]
    )

    assert exit_code == 2


def test_run_reference_cli_writes_replayable_trace(project_root, tmp_path):
    trace_output = tmp_path / "reference-v2.jsonl"
    exit_code = main(
        [
            "run-reference",
            "--dataset",
            str(project_root / "benchmarks/smoke/cases.jsonl"),
            "--config",
            str(project_root / "configs/evaluation.json"),
            "--version",
            "reference-v2",
            "--output",
            str(tmp_path / "artifact.json"),
            "--trace-output",
            str(trace_output),
        ]
    )

    assert exit_code == 0
    assert len(load_traces(trace_output)) == 15


def test_mutate_cli_generates_challenge_set(project_root, tmp_path):
    output = tmp_path / "challenge.jsonl"
    report = tmp_path / "challenge-report.json"
    exit_code = main(
        [
            "mutate",
            "--dataset",
            str(project_root / "benchmarks/smoke/cases.jsonl"),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )

    assert exit_code == 0
    assert report.is_file()
    challenge_cases = load_cases(output)
    assert len(challenge_cases) == 15
    assert all(case.dataset_split == "challenge" for case in challenge_cases)
    assert challenge_cases[0].case_id.startswith("challenge-")


def test_report_cli_renders_run_markdown(project_root, tmp_path):
    report_path = tmp_path / "run-report.md"
    exit_code = main(
        [
            "report",
            "--kind",
            "run",
            "--input",
            str(project_root / "artifacts/runs/round5-reference-v2.json"),
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    content = report_path.read_text(encoding="utf-8")
    assert "# 运行报告：reference-v2" in content
    assert "数据集分层切片" in content


def test_report_cli_renders_challenge_markdown(project_root, tmp_path):
    report_path = tmp_path / "challenge-report.md"
    exit_code = main(
        [
            "report",
            "--kind",
            "challenge",
            "--input",
            str(project_root / "artifacts/challenges/round6-report.json"),
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    content = report_path.read_text(encoding="utf-8")
    assert "# 挑战集报告" in content
    assert "变异类型" in content
