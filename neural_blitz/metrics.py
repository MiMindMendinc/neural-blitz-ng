"""Metrics model and persistence."""

from __future__ import annotations

import contextlib
import csv
import json
import os
import statistics
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neural_blitz.constants import SUPPORTED_METRICS_SUFFIXES, __version__
from neural_blitz.errors import MetricsError
from neural_blitz.latency import LatencyRecorder

CSV_FIELDNAMES = [
    "count_sent",
    "count_received",
    "count_lost",
    "count_retried",
    "count_duplicate",
    "count_malformed",
    "count_out_of_order",
    "success_rate",
    "loss_rate",
    "min_us",
    "max_us",
    "mean_us",
    "stddev_us",
    "p50_us",
    "p90_us",
    "p95_us",
    "p99_us",
    "p999_us",
    "p9999_us",
    "co_p50_us",
    "co_p99_us",
    "co_p999_us",
    "jitter_us",
    "duration_s",
    "pps",
    "loop_engine",
    "label",
    "host",
    "port",
    "timestamp_utc",
    "version",
]


@dataclass
class LatencyStats:
    count_sent: int = 0
    count_received: int = 0
    count_lost: int = 0
    count_retried: int = 0
    count_duplicate: int = 0
    count_malformed: int = 0
    count_out_of_order: int = 0
    success_rate: float = 0.0
    loss_rate: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    mean_us: float = 0.0
    stddev_us: float = 0.0
    p50_us: float = 0.0
    p90_us: float = 0.0
    p95_us: float = 0.0
    p99_us: float = 0.0
    p999_us: float = 0.0
    p9999_us: float = 0.0
    co_p50_us: float = 0.0
    co_p99_us: float = 0.0
    co_p999_us: float = 0.0
    jitter_us: float = 0.0
    duration_s: float = 0.0
    pps: float = 0.0
    loop_engine: str = "asyncio"
    label: str = "candidate"
    host: str = ""
    port: int = 0
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        return {key: round(value, 3) if isinstance(value, float) else value for key, value in asdict(self).items()}

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> LatencyStats:
        allowed = {f.name for f in fields(cls)}
        filtered = {key: raw[key] for key in raw if key in allowed}
        return cls(**filtered)


def compute_stats(
    recorder: LatencyRecorder,
    raw_rtts: list[float],
    *,
    count_sent: int,
    count_retried: int,
    count_duplicate: int,
    count_malformed: int,
    count_out_of_order: int,
    duration_s: float,
    loop_engine: str,
    label: str,
    host: str,
    port: int,
) -> LatencyStats:
    count_received = recorder.count
    count_lost = count_sent - count_received
    stats = LatencyStats(
        count_sent=count_sent,
        count_received=count_received,
        count_lost=count_lost,
        count_retried=count_retried,
        count_duplicate=count_duplicate,
        count_malformed=count_malformed,
        count_out_of_order=count_out_of_order,
        duration_s=duration_s,
        pps=count_sent / duration_s if duration_s > 0 else 0.0,
        loop_engine=loop_engine,
        label=label,
        host=host,
        port=port,
    )
    if count_sent:
        stats.success_rate = count_received / count_sent * 100.0
        stats.loss_rate = count_lost / count_sent * 100.0
    if recorder.count == 0:
        return stats
    stats.min_us = recorder.min_val
    stats.max_us = recorder.max_val
    stats.mean_us = recorder.mean
    stats.stddev_us = recorder.stddev
    stats.p50_us = recorder.percentile(50)
    stats.p90_us = recorder.percentile(90)
    stats.p95_us = recorder.percentile(95)
    stats.p99_us = recorder.percentile(99)
    stats.p999_us = recorder.percentile(99.9)
    stats.p9999_us = recorder.percentile(99.99)
    stats.co_p50_us = recorder.percentile(50, corrected=True)
    stats.co_p99_us = recorder.percentile(99, corrected=True)
    stats.co_p999_us = recorder.percentile(99.9, corrected=True)
    if len(raw_rtts) > 1:
        sorted_rtts = sorted(raw_rtts)
        stats.jitter_us = statistics.mean(abs(sorted_rtts[i + 1] - sorted_rtts[i]) for i in range(len(sorted_rtts) - 1))
    return stats


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_metrics(stats: LatencyStats, path: str) -> None:
    destination = Path(path).expanduser()
    data = stats.to_dict()
    try:
        if destination.suffix.lower() == ".csv":
            import io

            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            writer.writerow(data)
            _atomic_write_text(destination, buffer.getvalue())
        else:
            _atomic_write_text(destination, json.dumps(data, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        raise MetricsError(f"Unable to write metrics to '{destination}': {exc}") from exc


def load_metrics(path: str) -> LatencyStats:
    source = Path(path).expanduser()
    if not source.exists():
        raise MetricsError(f"Metrics file not found: {source}")
    try:
        if source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if not rows:
                raise MetricsError(f"Metrics CSV is empty: {source}")
            raw = rows[0]
        else:
            with source.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
    except OSError as exc:
        raise MetricsError(f"Unable to read metrics file '{source}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetricsError(f"Invalid JSON metrics file '{source}': {exc}") from exc
    if not isinstance(raw, dict):
        raise MetricsError(f"Metrics file '{source}' must contain a mapping")
    normalized: dict[str, Any] = {}
    int_fields = {
        "count_sent",
        "count_received",
        "count_lost",
        "count_retried",
        "count_duplicate",
        "count_malformed",
        "count_out_of_order",
        "port",
    }
    str_fields = {"loop_engine", "label", "host", "timestamp_utc", "version"}
    for key, value in raw.items():
        if value in ("", None):
            continue
        if key in str_fields:
            normalized[key] = str(value)
            continue
        if key in int_fields:
            normalized[key] = int(value)
            continue
        try:
            normalized[key] = float(value)
        except (TypeError, ValueError):
            normalized[key] = value
    return LatencyStats.from_mapping(normalized)


def validate_metrics_output_path(path: str) -> None:
    if not path:
        return
    suffix = Path(path).suffix.lower()
    if suffix and suffix not in SUPPORTED_METRICS_SUFFIXES:
        from neural_blitz.errors import ConfigError

        raise ConfigError("Metrics output must be .json or .csv")
