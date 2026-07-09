"""Tests for metrics comparison."""

import pytest

from neural_blitz.compare import ComparisonThresholds, compare_stats, evaluate_comparison
from neural_blitz.metrics import LatencyStats


@pytest.mark.unit
def test_compare_stats_delta():
    baseline = LatencyStats(p95_us=100.0, success_rate=99.0, label="base")
    candidate = LatencyStats(p95_us=120.0, success_rate=98.0, label="cand")
    rows = compare_stats(baseline, candidate)
    p95 = next(r for r in rows if r["metric"] == "p95_us")
    assert p95["delta"] == pytest.approx(20.0)


@pytest.mark.unit
def test_compare_regression_fail():
    baseline = LatencyStats(p95_us=100.0, loss_rate=0.5, success_rate=99.5)
    candidate = LatencyStats(p95_us=130.0, loss_rate=2.0, success_rate=97.0)
    thresholds = ComparisonThresholds(max_p95_regression_pct=20.0, max_loss_regression_pct=1.0)
    failures = evaluate_comparison(baseline, candidate, thresholds)
    assert failures
    assert any("p95_us" in f for f in failures)


@pytest.mark.unit
def test_compare_regression_pass():
    baseline = LatencyStats(p95_us=100.0, loss_rate=0.5)
    candidate = LatencyStats(p95_us=110.0, loss_rate=0.52)
    thresholds = ComparisonThresholds(max_p95_regression_pct=20.0, max_loss_regression_pct=5.0)
    assert evaluate_comparison(baseline, candidate, thresholds) == []
