"""Metrics comparison against baselines."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neural_blitz.errors import MetricsError
from neural_blitz.metrics import LatencyStats


@dataclass(frozen=True)
class ComparisonThresholds:
    max_p95_regression_pct: float | None = None
    max_p99_regression_pct: float | None = None
    max_loss_regression_pct: float | None = None
    max_success_regression_pct: float | None = None


def compare_stats(baseline: LatencyStats, candidate: LatencyStats) -> list[dict[str, Any]]:
    metrics = [
        "success_rate",
        "loss_rate",
        "mean_us",
        "p95_us",
        "p99_us",
        "p999_us",
        "co_p99_us",
        "jitter_us",
        "pps",
    ]
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        base_value = getattr(baseline, metric, 0.0)
        candidate_value = getattr(candidate, metric, 0.0)
        delta = candidate_value - base_value
        pct = (delta / base_value * 100.0) if base_value not in (0, 0.0) else None
        rows.append(
            {
                "metric": metric,
                "baseline": base_value,
                "candidate": candidate_value,
                "delta": delta,
                "delta_pct": pct,
            }
        )
    return rows


def evaluate_comparison(
    baseline: LatencyStats,
    candidate: LatencyStats,
    thresholds: ComparisonThresholds,
) -> list[str]:
    failures: list[str] = []
    rows = {row["metric"]: row for row in compare_stats(baseline, candidate)}

    def check_regression(metric: str, max_pct: float | None, worse_when_higher: bool) -> None:
        if max_pct is None:
            return
        row = rows[metric]
        delta_pct = row["delta_pct"]
        if delta_pct is None:
            return
        if worse_when_higher and delta_pct > max_pct:
            failures.append(
                f"{metric} regressed {delta_pct:.2f}% (limit {max_pct:.2f}%): "
                f"baseline={row['baseline']:.3f} candidate={row['candidate']:.3f}"
            )
        if not worse_when_higher and delta_pct < -max_pct:
            failures.append(
                f"{metric} regressed {abs(delta_pct):.2f}% (limit {max_pct:.2f}%): "
                f"baseline={row['baseline']:.3f} candidate={row['candidate']:.3f}"
            )

    check_regression("p95_us", thresholds.max_p95_regression_pct, worse_when_higher=True)
    check_regression("p99_us", thresholds.max_p99_regression_pct, worse_when_higher=True)
    check_regression("loss_rate", thresholds.max_loss_regression_pct, worse_when_higher=True)
    check_regression("success_rate", thresholds.max_success_regression_pct, worse_when_higher=False)
    return failures


def write_comparison_output(path: str, payload: dict[str, Any]) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destination.parent, prefix=".comparison.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, destination)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise MetricsError(f"Unable to write comparison output '{destination}': {exc}") from exc
