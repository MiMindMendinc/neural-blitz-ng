"""Monitor batch PDF/SLA path tests."""

import textwrap
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import run_batch_tests


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test")
@mock.patch("neural_blitz.monitor.write_pdf_report")
@mock.patch("neural_blitz.monitor.evaluate_sla", return_value=[])
@mock.patch("neural_blitz.monitor.load_sla")
async def test_batch_pdf_and_sla(mock_sla, mock_eval, mock_pdf, mock_run, tmp_path: Path):
    mock_run.return_value = LatencyStats(label="local", success_rate=100.0)
    sla_file = tmp_path / "sla.yaml"
    sla_file.write_text("min_success_rate: 99.0\n", encoding="utf-8")
    targets_file = tmp_path / "t.yaml"
    targets_file.write_text(
        textwrap.dedent(
            f"""
            targets:
              - label: local
                host: 127.0.0.1
                port: 9999
                sla_path: {sla_file}
                pdf_report: report.pdf
            """
        ),
        encoding="utf-8",
    )
    from neural_blitz.config import load_targets_file

    data = load_targets_file(str(targets_file))
    await run_batch_tests({}, data)
    mock_pdf.assert_called_once()


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.write_metrics")
@mock.patch("neural_blitz.monitor.write_pdf_report")
@mock.patch("neural_blitz.monitor.evaluate_sla", return_value=[])
@mock.patch("neural_blitz.monitor.load_sla")
@mock.patch("neural_blitz.monitor.run_test")
async def test_batch_applies_sla_alias_and_per_target_outputs(
    mock_run, mock_sla, mock_eval, mock_pdf, mock_metrics, tmp_path: Path
):
    stats = LatencyStats(label="local", success_rate=100.0, host="127.0.0.1", port=9999)
    mock_run.return_value = stats

    results = await run_batch_tests(
        {},
        {
            "__base_dir": str(tmp_path),
            "test": {"metrics_output": "target-metrics.json", "sla": "sla.yaml"},
            "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        },
        pdf_dir=str(tmp_path / "reports"),
    )

    assert results == [stats]
    mock_metrics.assert_called_once_with(stats, str(tmp_path / "target-metrics.json"))
    mock_sla.assert_called_once_with(str(tmp_path / "sla.yaml"))
    mock_eval.assert_called_once()
    mock_pdf.assert_called_once()
    assert mock_pdf.call_args.args[2] == str(tmp_path / "reports" / "local.pdf")


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.write_pdf_report")
@mock.patch("neural_blitz.monitor.run_test")
async def test_batch_writes_pdf_without_sla_evaluation(mock_run, mock_pdf, tmp_path: Path):
    stats = LatencyStats(label="local", success_rate=100.0, host="127.0.0.1", port=9999)
    mock_run.return_value = stats

    await run_batch_tests(
        {},
        {"targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}]},
        pdf_dir=str(tmp_path / "reports"),
    )

    assert mock_pdf.call_args.args[3] is None
