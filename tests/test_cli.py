from wikievalops.cli import main
from wikievalops.io import load_traces


def test_validate_cli(project_root, capsys):
    exit_code = main(["validate", str(project_root / "benchmarks/smoke/cases.jsonl")])

    assert exit_code == 0
    assert '"record_count": 12' in capsys.readouterr().out


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
    assert len(load_traces(trace_output)) == 12
