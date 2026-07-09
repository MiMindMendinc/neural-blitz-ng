"""Tests for latency packet encoding and histogram recording."""

import pytest

from neural_blitz.constants import HEADER_SIZE
from neural_blitz.latency import LatencyRecorder, build_packet, parse_packet


@pytest.mark.unit
def test_build_and_parse_packet_round_trip():
    packet = build_packet(seq_id=42, size=64, scheduled_ns=123456789)
    assert len(packet) == 64
    version, seq_id, send_ns, scheduled_ns = parse_packet(packet)
    assert version == 1
    assert seq_id == 42
    assert send_ns > 0
    assert scheduled_ns == 123456789


@pytest.mark.unit
def test_build_packet_minimum_header_size():
    packet = build_packet(seq_id=7, size=HEADER_SIZE)
    assert len(packet) == HEADER_SIZE
    assert parse_packet(packet)[1] == 7


@pytest.mark.unit
def test_parse_packet_rejects_too_small_packet():
    with pytest.raises(ValueError, match="too small"):
        parse_packet(b"too-small")


@pytest.mark.unit
def test_parse_packet_rejects_bad_version():
    packet = build_packet(1, 64)
    bad = bytes([99]) + packet[1:]
    with pytest.raises(ValueError, match="version"):
        parse_packet(bad)


@pytest.mark.unit
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


@pytest.mark.unit
def test_latency_recorder_coordinated_omission():
    recorder = LatencyRecorder()
    recorder.record_corrected(300.0, 100.0)
    assert recorder.percentile(99, corrected=True) >= recorder.percentile(99, corrected=False)


@pytest.mark.unit
def test_latency_recorder_empty_percentile():
    recorder = LatencyRecorder()
    assert recorder.percentile(50) == 0.0
