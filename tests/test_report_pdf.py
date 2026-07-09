"""PDF report tests."""

import pytest

from neural_blitz.config import TestConfig
from neural_blitz.metrics import LatencyStats
from neural_blitz.report_pdf import PDF_REPORTS_AVAILABLE, write_pdf_report


@pytest.mark.unit
@pytest.mark.skipif(not PDF_REPORTS_AVAILABLE, reason="reportlab not installed")
def test_write_pdf_report(tmp_path):
    stats = LatencyStats(label="pdf", count_sent=100, count_received=99, success_rate=99.0, p95_us=50.0)
    config = TestConfig(host="127.0.0.1", port=9999)
    path = tmp_path / "report.pdf"
    write_pdf_report(stats, config, str(path), sla_failures=[])
    assert path.exists()
    assert path.stat().st_size > 100


@pytest.mark.unit
@pytest.mark.skipif(not PDF_REPORTS_AVAILABLE, reason="reportlab not installed")
def test_write_pdf_report_with_sla_failures(tmp_path):
    stats = LatencyStats(label="pdf", success_rate=50.0)
    config = TestConfig()
    path = tmp_path / "fail.pdf"
    write_pdf_report(stats, config, str(path), sla_failures=["p95_us too high"])
    assert path.exists()
