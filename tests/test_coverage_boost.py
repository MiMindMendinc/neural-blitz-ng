"""Tests to reach coverage targets on client and CLI paths."""

from unittest import mock

import pytest

from neural_blitz.config import TestConfig
from neural_blitz.errors import DependencyMissing
from neural_blitz.report_pdf import ensure_pdf_reporting_available
from neural_blitz.safety import is_private_or_loopback
from neural_blitz.udp_client import ProgressReporter, run_test


@pytest.mark.unit
def test_is_private_network():
    assert is_private_or_loopback("10.0.0.1")
    assert is_private_or_loopback("192.168.1.1")


@pytest.mark.unit
def test_pdf_dependency_missing():
    with mock.patch("neural_blitz.report_pdf.PDF_REPORTS_AVAILABLE", False):
        with pytest.raises(DependencyMissing):
            ensure_pdf_reporting_available()


@pytest.mark.unit
def test_progress_reporter_plain():
    with ProgressReporter(10, enabled=True, use_rich=False) as progress:
        progress.update(True)
        progress.update(False)


@pytest.mark.unit
def test_progress_reporter_rich_branch():
    with ProgressReporter(5, enabled=True, use_rich=True) as progress:
        progress.update(True)


@pytest.mark.integration
async def test_run_test_with_warmup_and_rate(echo_server: int):
    config = TestConfig(
        host="127.0.0.1",
        port=echo_server,
        count=30,
        concurrency=5,
        rate=5000.0,
        warmup=5,
        progress_enabled=False,
    )
    stats = await run_test(config, use_rich=False)
    assert stats.count_received > 0


@pytest.mark.unit
def test_cli_main_metrics_error():
    from neural_blitz.cli import main
    from neural_blitz.errors import MetricsError

    with mock.patch("neural_blitz.cli.execute_compare", side_effect=MetricsError("bad metrics")):
        assert main(["--no-rich", "compare", "--baseline", "a.json", "--candidate", "b.json"]) == 1
