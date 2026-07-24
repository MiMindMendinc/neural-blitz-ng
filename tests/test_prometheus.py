"""Tests for Prometheus exposition."""

import pytest

from neural_blitz.metrics import LatencyStats
from neural_blitz.prometheus import METRIC_DESCRIPTORS, format_prometheus_metrics


@pytest.mark.unit
def test_prometheus_metric_names():
    stats = LatencyStats(
        label="local",
        host="127.0.0.1",
        port=9999,
        success_rate=99.5,
        loss_rate=0.5,
        p50_us=10.0,
        p95_us=20.0,
        p99_us=30.0,
        jitter_us=5.0,
        count_sent=100,
        count_received=99,
        count_lost=1,
    )
    text = format_prometheus_metrics({"local": stats})
    assert "neural_blitz_success_rate_percent" in text
    assert "neural_blitz_latency_p95_us" in text
    assert 'label="local"' in text
    assert 'host="127.0.0.1"' in text
    assert 'port="9999"' in text
    assert "neural_blitz_target_up" in text
    assert "# TYPE neural_blitz_success_rate_percent gauge" in text
    assert "neural_blitz_last_run_timestamp_seconds" in text
    assert '"202' not in text
    for descriptor in METRIC_DESCRIPTORS:
        assert text.count(f"# HELP {descriptor.name} ") == 1
        assert text.count(f"# TYPE {descriptor.name} {descriptor.metric_type}") == 1
        assert text.count(f"{descriptor.name}{{") == 1


@pytest.mark.unit
def test_prometheus_snapshot_packet_counts_are_gauges():
    text = format_prometheus_metrics({"local": LatencyStats(count_sent=10, count_received=8, count_lost=2)})
    for name in (
        "neural_blitz_packets_sent_total",
        "neural_blitz_packets_received_total",
        "neural_blitz_packets_lost_total",
    ):
        assert f"# TYPE {name} gauge" in text


@pytest.mark.unit
def test_prometheus_escapes_labels_and_timestamp_is_numeric():
    stats = LatencyStats(label='a"b', host="host\\name", timestamp_utc="2026-01-01T00:00:00+00:00")
    text = format_prometheus_metrics({'a"b': stats})
    assert 'label="a\\"b"' in text
    assert 'host="host\\\\name"' in text
    assert "1767225600.000000" in text


@pytest.mark.unit
def test_prometheus_uses_zero_for_invalid_timestamp():
    text = format_prometheus_metrics({"local": LatencyStats(timestamp_utc="not-a-date")})
    assert "neural_blitz_last_run_timestamp_seconds" in text
    assert " 0.000000" in text
