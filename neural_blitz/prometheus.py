"""Prometheus text exposition format."""

from __future__ import annotations

from datetime import datetime

from neural_blitz.metrics import LatencyStats


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _timestamp_seconds(timestamp: str) -> float:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def format_prometheus_metrics(latest: dict[str, LatencyStats]) -> str:
    lines: list[str] = [
        "# HELP neural_blitz_success_rate_percent Percentage of packets that received a response.",
        "# TYPE neural_blitz_success_rate_percent gauge",
        "# HELP neural_blitz_loss_rate_percent Percentage of packets without a response.",
        "# TYPE neural_blitz_loss_rate_percent gauge",
        "# HELP neural_blitz_latency_p95_us UDP round-trip latency at p95 in microseconds.",
        "# TYPE neural_blitz_latency_p95_us gauge",
        "# HELP neural_blitz_target_up Target produced at least one response in its latest run.",
        "# TYPE neural_blitz_target_up gauge",
        "# HELP neural_blitz_last_run_timestamp_seconds Unix timestamp of the latest completed run.",
        "# TYPE neural_blitz_last_run_timestamp_seconds gauge",
    ]
    for label, stats in sorted(latest.items()):
        host = stats.host or "unknown"
        port = str(stats.port or 0)
        common = f'label="{_escape_label(label)}",host="{_escape_label(host)}",port="{_escape_label(port)}"'
        target_up = f"neural_blitz_target_up{{{common}}} {1 if stats.success_rate > 0 else 0}"
        lines.extend(
            [
                f"neural_blitz_success_rate_percent{{{common}}} {stats.success_rate:.6f}",
                f"neural_blitz_loss_rate_percent{{{common}}} {stats.loss_rate:.6f}",
                f"neural_blitz_latency_p50_us{{{common}}} {stats.p50_us:.6f}",
                f"neural_blitz_latency_p95_us{{{common}}} {stats.p95_us:.6f}",
                f"neural_blitz_latency_p99_us{{{common}}} {stats.p99_us:.6f}",
                f"neural_blitz_jitter_us{{{common}}} {stats.jitter_us:.6f}",
                f"neural_blitz_packets_sent_total{{{common}}} {stats.count_sent}",
                f"neural_blitz_packets_received_total{{{common}}} {stats.count_received}",
                f"neural_blitz_packets_lost_total{{{common}}} {stats.count_lost}",
                target_up,
                f"neural_blitz_last_run_timestamp_seconds{{{common}}} {_timestamp_seconds(stats.timestamp_utc):.6f}",
            ]
        )
    return "\n".join(lines) + ("\n" if lines else "")
