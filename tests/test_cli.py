from wikievalops.cli import main


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
