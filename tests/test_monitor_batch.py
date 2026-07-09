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
