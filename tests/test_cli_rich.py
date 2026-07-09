"""CLI Rich rendering tests."""

from unittest import mock

import pytest

from neural_blitz.cli import render_batch_results, render_comparison, render_stats
from neural_blitz.metrics import LatencyStats


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.console")
def test_render_stats_rich(mock_console):
    render_stats(LatencyStats(label="r", success_rate=99.0), use_rich=True, as_json=False)
    mock_console.print.assert_called_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.console")
def test_render_batch_rich(mock_console):
    render_batch_results([LatencyStats(label="a", success_rate=99.0)], use_rich=True, as_json=False)
    mock_console.print.assert_called_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.console")
def test_render_comparison_rich(mock_console):
    base = LatencyStats(label="b")
    cand = LatencyStats(label="c")
    rows = [{"metric": "p95_us", "baseline": 1.0, "candidate": 2.0, "delta": 1.0, "delta_pct": 100.0}]
    render_comparison(base, cand, rows, use_rich=True, as_json=False, failures=["x"])
    mock_console.print.assert_called_once()
