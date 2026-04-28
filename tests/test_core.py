import pytest

from neural_blitz_ng import (
    HEADER_SIZE,
    ConfigError,
    LatencyRecorder,
    LatencyStats,
    TestConfig,
    build_packet,
    parse_packet,
    validate_test_config,
)


def test_build_and_parse_packet_round_trip():
    packet = build_packet(seq_id=42, size=64, scheduled_ns=123456789)

    assert len(packet) == 64

    seq_id, send_ns, scheduled_ns = parse_packet(packet)
    assert seq_id == 42
    assert send_ns > 0
    assert scheduled_ns == 123456789


def test_build_packet_minimum_header_size():
    packet = build_packet(seq_id=7, size=HEADER_SIZE)

    assert len(packet) == HEADER_SIZE
    assert parse_packet(packet)[0] == 7


def test_parse_packet_rejects_too_small_packet():
    with pytest.raises(ValueError):
        parse_packet(b"too-small")


def test_latency_recorder_tracks_basic_stats():
    recorder = LatencyRecorder()
    recorder.record(100.0)
    recorder.record(200.0)
    recorder.record(300.0)

    assert recorder.count == 3
    assert recorder.min_val == 100.0
    assert recorder.max_val == 300.0
    assert recorder.mean == pytest.approx(200.0)
    assert recorder.stddev > 0.0
    assert recorder.percentile(50) > 0.0


def test_latency_stats_to_dict_rounds_float_values():
    stats = LatencyStats(mean_us=12.34567, p99_us=98.76543, label="local")

    data = stats.to_dict()

    assert data["mean_us"] == 12.346
    assert data["p99_us"] == 98.765
    assert data["label"] == "local"


def test_validate_test_config_accepts_valid_defaults():
    validate_test_config(TestConfig())


def test_validate_test_config_rejects_invalid_port():
    with pytest.raises(ConfigError):
        validate_test_config(TestConfig(port=70000))


def test_validate_test_config_rejects_too_small_packet():
    with pytest.raises(ConfigError):
        validate_test_config(TestConfig(size=HEADER_SIZE - 1))
