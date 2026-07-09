"""Extended CLI and command handler tests."""

import json
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz.cli import main
from neural_blitz.metrics import LatencyStats, write_metrics


@pytest.mark.unit
def test_cli_init_config(tmp_path: Path, capsys):
    out = tmp_path / "sample.yaml"
    assert main(["--no-rich", "init-config", "--output", str(out)]) == 0
    assert out.exists()
    assert "targets:" in out.read_text(encoding="utf-8")


@pytest.mark.unit
def test_cli_validate_config_valid(tmp_path: Path, capsys):
    cfg = tmp_path / "ok.yaml"
    cfg.write_text("targets:\n  - label: local\n    host: 127.0.0.1\n    port: 9999\n", encoding="utf-8")
    assert main(["validate-config", str(cfg)]) == 0
    assert "valid" in capsys.readouterr().out.lower()


@pytest.mark.unit
def test_cli_validate_sla_valid():
    assert main(["validate-sla", "examples/sla.yaml"]) == 0


@pytest.mark.unit
def test_cli_compare_json(tmp_path: Path, capsys):
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    write_metrics(LatencyStats(label="base", p95_us=100.0, success_rate=99.0), str(base))
    write_metrics(LatencyStats(label="cand", p95_us=105.0, success_rate=98.5), str(cand))
    assert main(["--no-rich", "compare", "--baseline", str(base), "--candidate", str(cand), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True


@pytest.mark.unit
def test_cli_compare_fail_on_regression(tmp_path: Path):
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    write_metrics(LatencyStats(p95_us=100.0, loss_rate=0.5), str(base))
    write_metrics(LatencyStats(p95_us=200.0, loss_rate=2.0), str(cand))
    assert (
        main(
            [
                "--no-rich",
                "compare",
                "--baseline",
                str(base),
                "--candidate",
                str(cand),
                "--max-p95-regression",
                "10",
                "--fail-on-regression",
                "--json",
            ]
        )
        == 4
    )


@pytest.mark.unit
def test_cli_test_safety_violation(capsys):
    code = main(
        [
            "--no-rich",
            "test",
            "--host",
            "8.8.8.8",
            "--port",
            "53",
            "--count",
            "10",
            "--concurrency",
            "1",
            "--warmup",
            "0",
            "--no-progress",
        ]
    )
    assert code == 5


@pytest.mark.unit
@mock.patch("neural_blitz.cli.asyncio.run")
def test_cli_test_localhost(mock_run, capsys):
    mock_run.return_value = LatencyStats(success_rate=100.0, count_received=10, count_sent=10)
    code = main(
        [
            "--no-rich",
            "test",
            "--host",
            "127.0.0.1",
            "--port",
            "9999",
            "--count",
            "10",
            "--concurrency",
            "1",
            "--warmup",
            "0",
            "--no-progress",
            "--json",
        ]
    )
    assert code == 0
    assert '"success_rate"' in capsys.readouterr().out


@pytest.mark.unit
def test_cli_validate_config_json_invalid(capsys):
    assert main(["validate-config", "/missing.yaml", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
