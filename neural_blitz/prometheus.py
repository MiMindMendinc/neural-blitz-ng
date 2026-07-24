"""Prometheus text exposition format."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from neural_blitz.metrics import LatencyStats


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _timestamp_seconds(timestamp: str) -> float:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


@dataclass(frozen=True)
class MetricDescriptor:
    """A Prometheus metric family emitted for every latest-run snapshot."""

    name: str
    metric_type: str
    help: str
    value: Callable[[LatencyStats], float | int]


METRIC_DESCRIPTORS: tuple[MetricDescriptor, ...] = (
    MetricDescriptor(
        "neural_blitz_success_rate_percent",
        "gauge",
        "Percentage of packets that received a response in the latest run.",
        lambda stats: stats.success_rate,
    ),
    MetricDescriptor(
        "neural_blitz_loss_rate_percent",
        "gauge",
        "Percentage of packets without a response in the latest run.",
        lambda stats: stats.loss_rate,
    ),
    MetricDescriptor(
        "neural_blitz_latency_p50_us",
        "gauge",
        "Latest-run UDP round-trip latency p50 in microseconds.",
        lambda stats: stats.p50_us,
    ),
    MetricDescriptor(
        "neural_blitz_latency_p95_us",
        "gauge",
        "Latest-run UDP round-trip latency p95 in microseconds.",
        lambda stats: stats.p95_us,
    ),
    MetricDescriptor(
        "neural_blitz_latency_p99_us",
        "gauge",
        "Latest-run UDP round-trip latency p99 in microseconds.",
        lambda stats: stats.p99_us,
    ),
    MetricDescriptor(
        "neural_blitz_jitter_us",
        "gauge",
        "Latest-run UDP round-trip jitter in microseconds.",
        lambda stats: stats.jitter_us,
    ),
    # These are per-run snapshot counts, not monotonically increasing process counters.
    # The established `_total` names are retained for dashboard compatibility.
    MetricDescriptor(
        "neural_blitz_packets_sent_total",
        "gauge",
        "Packets sent in the latest run.",
        lambda stats: stats.count_sent,
    ),
    MetricDescriptor(
        "neural_blitz_packets_received_total",
        "gauge",
        "Packets received in the latest run.",
        lambda stats: stats.count_received,
    ),
    MetricDescriptor(
        "neural_blitz_packets_lost_total",
        "gauge",
        "Packets lost in the latest run.",
        lambda stats: stats.count_lost,
    ),
    MetricDescriptor(
        "neural_blitz_target_up",
        "gauge",
        "Whether the target produced at least one response in its latest run.",
        lambda stats: 1 if stats.success_rate > 0 else 0,
    ),
    MetricDescriptor(
        "neural_blitz_last_run_timestamp_seconds",
        "gauge",
        "Unix timestamp of the latest completed run.",
        lambda stats: _timestamp_seconds(stats.timestamp_utc),
    ),
)


def format_prometheus_metrics(latest: dict[str, LatencyStats]) -> str:
    lines = [f"# HELP {descriptor.name} {descriptor.help}" for descriptor in METRIC_DESCRIPTORS]
    lines.extend(f"# TYPE {descriptor.name} {descriptor.metric_type}" for descriptor in METRIC_DESCRIPTORS)
    for label, stats in sorted(latest.items()):
        host = stats.host or "unknown"
        port = str(stats.port or 0)
        common = f'label="{_escape_label(label)}",host="{_escape_label(host)}",port="{_escape_label(port)}"'
        for descriptor in METRIC_DESCRIPTORS:
            value = descriptor.value(stats)
            rendered = str(value) if isinstance(value, int) else f"{value:.6f}"
            lines.append(f"{descriptor.name}{{{common}}} {rendered}")
    return "\n".join(lines) + ("\n" if lines else "")
