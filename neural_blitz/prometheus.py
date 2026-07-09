"""Prometheus text exposition format."""

from __future__ import annotations

from neural_blitz.metrics import LatencyStats


def format_prometheus_metrics(latest: dict[str, LatencyStats]) -> str:
    lines: list[str] = []
    for label, stats in sorted(latest.items()):
        host = stats.host or "unknown"
        port = str(stats.port or 0)
        common = f'label="{label}",host="{host}",port="{port}"'
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
                f'neural_blitz_target_up{{label="{label}",host="{host}",port="{port}"}} '
                f"{1 if stats.success_rate > 0 else 0}",
                f'neural_blitz_last_run_timestamp{{label="{label}",host="{host}",port="{port}"}} '
                f'"{stats.timestamp_utc}"',
            ]
        )
    return "\n".join(lines) + ("\n" if lines else "")
