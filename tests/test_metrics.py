"""Tests for metrics model and persistence."""

import json
from pathlib import Path

import pytest

from neural_blitz.latency import LatencyRecorder
from neural_blitz.metrics import LatencyStats, compute_stats, load_metrics, write_metrics


@pytest.mark.unit
def test_latency_stats_to_dict_rounds_float_values():
    stats = LatencyStats(mean_us=12.34567, p99_us=98.76543, label="local")
    data = stats.to_dict()
    assert data["mean_us"] == 12.346
    assert data["p99_us"] == 98.765
    assert data["label"] == "local"


@pytest.mark.unit
def test_compute_stats_includes_loss_rate():
    recorder = LatencyRecorder()
    recorder.record(100.0)
    stats = compute_stats(
        recorder,
        [100.0],
        count_sent=10,
        count_retried=0,
        count_duplicate=0,
        count_malformed=0,
        count_out_of_order=0,
        duration_s=1.0,
        loop_engine="asyncio",
        label="t",
        host="127.0.0.1",
        port=9999,
    )
    assert stats.count_lost == 9
    assert stats.success_rate == pytest.approx(10.0)
    assert stats.loss_rate == pytest.approx(90.0)


@pytest.mark.unit
def test_metrics_json_round_trip(tmp_path: Path):
    stats = LatencyStats(label="roundtrip", count_sent=100, count_received=99, host="127.0.0.1", port=9999)
    path = tmp_path / "m.json"
    write_metrics(stats, str(path))
    loaded = load_metrics(str(path))
    assert loaded.label == "roundtrip"
    assert loaded.count_sent == 100
    assert loaded.host == "127.0.0.1"


@pytest.mark.unit
def test_metrics_csv_round_trip(tmp_path: Path):
    stats = LatencyStats(label="csv", count_sent=50, p95_us=123.456)
    path = tmp_path / "m.csv"
    write_metrics(stats, str(path))
    loaded = load_metrics(str(path))
    assert loaded.label == "csv"
    assert loaded.p95_us == pytest.approx(123.456, rel=1e-3)


@pytest.mark.unit
def test_metrics_json_is_pretty(tmp_path: Path):
    path = tmp_path / "m.json"
    write_metrics(LatencyStats(), str(path))
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)
