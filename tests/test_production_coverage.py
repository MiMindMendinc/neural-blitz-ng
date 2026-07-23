"""Behavioral tests for validation and error paths used in production."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from neural_blitz.compare import ComparisonThresholds, evaluate_comparison, write_comparison_output
from neural_blitz.config import (
    MonitorConfig,
    ServerConfig,
    TestConfig,
    validate_monitor_config,
    validate_server_config,
    validate_test_config,
)
from neural_blitz.constants import HEADER_SIZE
from neural_blitz.errors import ConfigError, MetricsError, SafetyViolation
from neural_blitz.latency import LatencyRecorder
from neural_blitz.metrics import LatencyStats, load_metrics, validate_metrics_output_path, write_metrics
from neural_blitz.safety import SafetyLimits, is_private_or_loopback, validate_test_safety
from neural_blitz.sla import SLAConfig, load_sla, validate_sla_config


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", 0),
        ("concurrency", 0),
        ("timeout", 0),
        ("rate", -1),
        ("max_retries", -1),
        ("warmup", -1),
        ("socket_rcvbuf", 0),
        ("socket_sndbuf", 0),
        ("pdf_report", "report.txt"),
    ],
)
def test_test_config_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ConfigError):
        validate_test_config(TestConfig(**{field: value}))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "config",
    [
        ServerConfig(port=0),
        ServerConfig(max_packet_size=HEADER_SIZE - 1),
        ServerConfig(rate_limit=-1),
    ],
)
def test_server_config_rejects_invalid_values(config: ServerConfig) -> None:
    with pytest.raises(ConfigError):
        validate_server_config(config)


@pytest.mark.parametrize(
    "config",
    [MonitorConfig(http_port=0), MonitorConfig(history_limit=0), MonitorConfig(stale_after_seconds=0)],
)
def test_monitor_config_rejects_invalid_values(config: MonitorConfig) -> None:
    with pytest.raises(ConfigError):
        validate_monitor_config(config)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"concurrency": 2}, "concurrency"),
        ({"size": 2}, "packet size"),
    ],
)
def test_safety_enforces_remaining_limits(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(SafetyViolation, match=message):
        validate_test_safety(
            host="127.0.0.1",
            count=1,
            size=kwargs.get("size", 64),
            concurrency=kwargs.get("concurrency", 1),
            timeout=1,
            rate=1,
            authorized_target=False,
            limits=SafetyLimits(max_concurrency=1, max_packet_size=1 if "size" in kwargs else 64),
        )


def test_safety_rejects_non_ip_host_without_authorization() -> None:
    assert is_private_or_loopback("not an ip") is False


def test_latency_bucket_clamps_and_percentile_upper_bound() -> None:
    recorder = LatencyRecorder()
    assert recorder._bucket_for(0.5) == 0
    assert recorder._bucket_for(4_000_000_000) == recorder._BUCKET_COUNT - 1
    recorder.record(4_000_000_000)
    assert recorder.percentile(100) == recorder._value_for(recorder._BUCKET_COUNT - 1)


def test_comparison_handles_zero_baseline_and_success_regression() -> None:
    baseline = LatencyStats(p95_us=0, success_rate=99)
    candidate = LatencyStats(p95_us=10, success_rate=97)
    failures = evaluate_comparison(
        baseline,
        candidate,
        ComparisonThresholds(max_p95_regression_pct=1, max_success_regression_pct=1),
    )
    assert len(failures) == 1 and "success_rate" in failures[0]


def test_comparison_write_error_is_wrapped(tmp_path: Path) -> None:
    with patch("neural_blitz.compare.os.replace", side_effect=OSError("denied")), pytest.raises(MetricsError):
        write_comparison_output(str(tmp_path / "out.json"), {"ok": True})


@pytest.mark.parametrize("contents", ["[]", "{bad"])
def test_metrics_load_rejects_invalid_documents(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "metrics.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(MetricsError):
        load_metrics(str(path))


def test_metrics_write_error_and_empty_output_path(tmp_path: Path) -> None:
    validate_metrics_output_path("")
    with patch("neural_blitz.metrics._atomic_write_text", side_effect=OSError("denied")), pytest.raises(MetricsError):
        write_metrics(LatencyStats(), str(tmp_path / "metrics.json"))


def test_sla_validation_and_non_mapping_file(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("not-a-mapping", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_sla(str(path))
    assert validate_sla_config(SLAConfig(max_loss_rate=101, max_p95_us=-1, min_pps=-1))
