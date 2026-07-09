"""UDP packet encoding and latency histogram recording."""

from __future__ import annotations

import math
import time

from neural_blitz.constants import HEADER_SIZE, HEADER_STRUCT, PACKET_VERSION


def build_packet(seq_id: int, size: int, scheduled_ns: int = 0) -> bytes:
    ts = time.monotonic_ns()
    header = HEADER_STRUCT.pack(PACKET_VERSION, seq_id, ts, scheduled_ns or ts)
    return header + b"\x00" * max(0, size - HEADER_SIZE)


def parse_packet(data: bytes) -> tuple[int, int, int, int]:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Packet too small: {len(data)} < {HEADER_SIZE}")
    version, seq_id, send_ns, sched_ns = HEADER_STRUCT.unpack_from(data)
    if version != PACKET_VERSION:
        raise ValueError(f"Unsupported packet version: {version}")
    return version, seq_id, send_ns, sched_ns


class LatencyRecorder:
    """Bucketed histogram recorder with optional coordinated-omission correction."""

    __slots__ = ("_counts", "_total", "_min", "_max", "_sum", "_sum_sq", "_co_counts", "_co_total")

    _PRECISION = 3
    _MIN_VALUE = 1
    _MAX_VALUE = 3_600_000_000
    _BUCKET_COUNT = int(math.log2(_MAX_VALUE / _MIN_VALUE) * _PRECISION) + 2

    def __init__(self) -> None:
        self._counts = [0] * self._BUCKET_COUNT
        self._total = 0
        self._min = float("inf")
        self._max = 0.0
        self._sum = 0.0
        self._sum_sq = 0.0
        self._co_counts = [0] * self._BUCKET_COUNT
        self._co_total = 0

    def _bucket_for(self, value_us: float) -> int:
        if value_us <= self._MIN_VALUE:
            return 0
        if value_us >= self._MAX_VALUE:
            return self._BUCKET_COUNT - 1
        return min(int(math.log2(value_us / self._MIN_VALUE) * self._PRECISION), self._BUCKET_COUNT - 1)

    def _value_for(self, bucket: int) -> float:
        return float(self._MIN_VALUE * (2.0 ** (bucket / self._PRECISION)))

    def record(self, value_us: float) -> None:
        bucket = self._bucket_for(value_us)
        self._counts[bucket] += 1
        self._total += 1
        self._min = min(self._min, value_us)
        self._max = max(self._max, value_us)
        self._sum += value_us
        self._sum_sq += value_us * value_us

    def record_corrected(self, value_us: float, expected_interval_us: float) -> None:
        self.record(value_us)
        bucket = self._bucket_for(value_us)
        self._co_counts[bucket] += 1
        self._co_total += 1
        if expected_interval_us <= 0 or value_us <= expected_interval_us:
            return
        missing = value_us - expected_interval_us
        while missing >= expected_interval_us:
            missing_bucket = self._bucket_for(missing)
            self._co_counts[missing_bucket] += 1
            self._co_total += 1
            missing -= expected_interval_us

    def percentile(self, percentile: float, corrected: bool = False) -> float:
        counts = self._co_counts if corrected else self._counts
        total = self._co_total if corrected else self._total
        if total == 0:
            return 0.0
        target = (percentile / 100.0) * total
        cumulative = 0
        for index, count in enumerate(counts):
            cumulative += count
            if cumulative >= target:
                return self._value_for(index)
        return float(self._value_for(self._BUCKET_COUNT - 1))

    @property
    def count(self) -> int:
        return self._total

    @property
    def mean(self) -> float:
        return self._sum / self._total if self._total else 0.0

    @property
    def stddev(self) -> float:
        if self._total < 2:
            return 0.0
        variance = (self._sum_sq / self._total) - (self.mean**2)
        return math.sqrt(max(0.0, variance))

    @property
    def min_val(self) -> float:
        return self._min if self._total else 0.0

    @property
    def max_val(self) -> float:
        return self._max
