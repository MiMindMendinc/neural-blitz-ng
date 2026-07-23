"""Behavioral coverage for remaining metrics, reporting, and safety paths."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from neural_blitz.config import TestConfig
from neural_blitz.errors import MetricsError, SafetyViolation
from neural_blitz.latency import LatencyRecorder
from neural_blitz.metrics import LatencyStats, _atomic_write_text, compute_stats, load_metrics
from neural_blitz.safety import SafetyLimits, log_responsible_use_notice
from neural_blitz.sla import SLAConfig, load_sla


@pytest.mark.unit
def test_configure_logging_rich_uses_rich_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.logging_setup as logging_setup

    class FakeRichHandler(logging.Handler):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()
            self.kwargs = kwargs

        def emit(self, record: logging.LogRecord) -> None:
            pass

    fake_console = object()
    monkeypatch.setattr(logging_setup, "RICH_AVAILABLE", True)
    monkeypatch.setattr(logging_setup, "RichHandler", FakeRichHandler)
    monkeypatch.setattr(logging_setup, "error_console", fake_console)

    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        logging_setup.configure_logging("warning", use_rich=True)
        handler = root.handlers[0]
        assert isinstance(handler, FakeRichHandler)
        assert handler.kwargs["console"] is fake_console
        assert handler.formatter is not None
        assert handler.formatter._style._fmt == "%(message)s"
    finally:
        root.handlers = original_handlers


@pytest.mark.unit
def test_emit_error_uses_rich_panel_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.logging_setup as logging_setup

    error_console = Mock()
    panel = Mock()
    panel.fit.return_value = "formatted error"
    monkeypatch.setattr(logging_setup, "RICH_AVAILABLE", True)
    monkeypatch.setattr(logging_setup, "error_console", error_console)
    monkeypatch.setitem(sys.modules, "rich.panel", SimpleNamespace(Panel=panel))

    logging_setup.emit_error("database unavailable", use_rich=True)

    panel.fit.assert_called_once_with("database unavailable", title="Error", style="bold red")
    error_console.print.assert_called_once()


@pytest.mark.unit
def test_compute_stats_empty_recorder_and_zero_duration() -> None:
    stats = compute_stats(
        LatencyRecorder(),
        [],
        count_sent=0,
        count_retried=1,
        count_duplicate=2,
        count_malformed=3,
        count_out_of_order=4,
        duration_s=0,
        loop_engine="asyncio",
        label="empty",
        host="localhost",
        port=9999,
    )

    assert stats.pps == 0
    assert stats.success_rate == 0
    assert stats.min_us == 0


@pytest.mark.unit
def test_compute_stats_calculates_jitter_from_sorted_samples() -> None:
    recorder = LatencyRecorder()
    for value in (10.0, 20.0, 30.0):
        recorder.record(value)

    stats = compute_stats(
        recorder,
        [30.0, 10.0, 20.0],
        count_sent=3,
        count_retried=0,
        count_duplicate=0,
        count_malformed=0,
        count_out_of_order=0,
        duration_s=2,
        loop_engine="asyncio",
        label="jitter",
        host="localhost",
        port=9999,
    )

    assert stats.jitter_us == pytest.approx(10.0)


@pytest.mark.unit
def test_atomic_write_removes_temporary_file_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import neural_blitz.metrics as metrics

    destination = tmp_path / "metrics.json"
    monkeypatch.setattr(metrics.os, "replace", Mock(side_effect=OSError("read-only")))

    with pytest.raises(OSError, match="read-only"):
        _atomic_write_text(destination, "data")

    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.unit
def test_load_metrics_wraps_read_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.metrics as metrics

    source = tmp_path / "metrics.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "open", Mock(side_effect=OSError("denied")))

    with pytest.raises(MetricsError, match="Unable to read"):
        metrics.load_metrics(str(source))


@pytest.mark.unit
def test_load_metrics_preserves_unparseable_known_value(tmp_path: Path) -> None:
    source = tmp_path / "metrics.json"
    source.write_text('{"mean_us": "unavailable", "ignored": "value"}', encoding="utf-8")

    stats = load_metrics(str(source))

    assert stats.mean_us == "unavailable"


@pytest.mark.unit
def test_safety_rejects_invalid_float_environment_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEURAL_BLITZ_MAX_RATE", "fast")

    with pytest.raises(SafetyViolation, match="NEURAL_BLITZ_MAX_RATE"):
        SafetyLimits.from_env()


@pytest.mark.unit
def test_safety_float_override_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEURAL_BLITZ_MAX_RATE", "42.5")

    with pytest.warns(UserWarning, match="NEURAL_BLITZ_MAX_RATE"):
        limits = SafetyLimits.from_env()

    assert limits.max_rate == 42.5


@pytest.mark.unit
def test_responsible_use_notice_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="neural_blitz"):
        log_responsible_use_notice()

    assert "authorized network monitoring" in caplog.text


@pytest.mark.unit
def test_load_sla_uses_nested_section_and_ignores_unknown_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.sla as sla_module

    monkeypatch.setattr(
        sla_module,
        "load_config",
        lambda _: {"sla": {"min_success_rate": 99.9, "max_p95_us": 10, "unrelated": True}},
    )

    assert load_sla("ignored.yaml") == SLAConfig(min_success_rate=99.9, max_p95_us=10)


@pytest.mark.unit
def test_load_sla_uses_top_level_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.sla as sla_module

    monkeypatch.setattr(sla_module, "load_config", lambda _: {"min_pps": 1000})

    assert load_sla("ignored.yaml") == SLAConfig(min_pps=1000)


@pytest.mark.unit
def test_latency_percentile_above_hundred_returns_final_bucket() -> None:
    recorder = LatencyRecorder()
    recorder.record(10.0)

    assert recorder.percentile(101) == recorder._value_for(recorder._BUCKET_COUNT - 1)


@pytest.mark.unit
def test_pdf_report_wraps_document_write_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.report_pdf as report_pdf

    class FakeTable:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def setStyle(self, _: object) -> None:
            pass

    class FailingDocument:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def build(self, _: list[object]) -> None:
            raise OSError("disk full")

    monkeypatch.setattr(report_pdf, "PDF_REPORTS_AVAILABLE", True)
    monkeypatch.setattr(report_pdf, "colors", SimpleNamespace(HexColor=lambda value: value), raising=False)
    monkeypatch.setattr(report_pdf, "letter", "letter", raising=False)
    monkeypatch.setattr(report_pdf, "inch", 1, raising=False)
    monkeypatch.setattr(
        report_pdf,
        "getSampleStyleSheet",
        lambda: {"Title": object(), "BodyText": object(), "Heading2": object()},
        raising=False,
    )
    monkeypatch.setattr(report_pdf, "ParagraphStyle", lambda *_args, **_kwargs: object(), raising=False)
    monkeypatch.setattr(report_pdf, "Paragraph", lambda *_args: object(), raising=False)
    monkeypatch.setattr(report_pdf, "Spacer", lambda *_args: object(), raising=False)
    monkeypatch.setattr(report_pdf, "PdfTable", FakeTable, raising=False)
    monkeypatch.setattr(report_pdf, "TableStyle", lambda value: value, raising=False)
    monkeypatch.setattr(report_pdf, "SimpleDocTemplate", FailingDocument, raising=False)

    with pytest.raises(MetricsError, match="Unable to write PDF report"):
        report_pdf.write_pdf_report(LatencyStats(), TestConfig(), str(tmp_path / "report.pdf"))
