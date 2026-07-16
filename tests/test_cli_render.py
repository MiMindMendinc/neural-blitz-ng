"""CLI batch/monitor and render path tests."""

from argparse import Namespace
from unittest import mock

import pytest

from neural_blitz.cli import (
    execute_batch,
    execute_monitor,
    execute_test,
    render_batch_results,
    render_comparison,
    render_sla_result,
    render_stats,
)
from neural_blitz.metrics import LatencyStats


@pytest.mark.unit
def test_render_stats_plain_json(capsys):
    render_stats(LatencyStats(label="x", success_rate=99.0), use_rich=False, as_json=True)
    assert '"label"' in capsys.readouterr().out


@pytest.mark.unit
def test_render_sla_pass_plain(capsys):
    render_sla_result([], "sla.yaml", use_rich=False)
    assert "PASS" in capsys.readouterr().out


@pytest.mark.unit
def test_render_sla_fail_plain(capsys):
    render_sla_result(["bad"], "sla.yaml", use_rich=False)
    assert "FAIL" in capsys.readouterr().err


@pytest.mark.unit
def test_render_comparison_plain(capsys):
    base = LatencyStats(label="b", p95_us=1.0)
    cand = LatencyStats(label="c", p95_us=2.0)
    rows = [{"metric": "p95_us", "baseline": 1.0, "candidate": 2.0, "delta": 1.0, "delta_pct": 100.0}]
    render_comparison(base, cand, rows, use_rich=False, as_json=True)
    assert '"comparison"' in capsys.readouterr().out


@pytest.mark.unit
def test_render_batch_results_json(capsys):
    render_batch_results([LatencyStats(label="a")], use_rich=False, as_json=True)
    assert '"label"' in capsys.readouterr().out


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_batch_tests", new_callable=mock.AsyncMock)
@mock.patch("neural_blitz.cli.load_targets_file")
def test_execute_batch(mock_load, mock_run_batch):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": ".",
    }
    mock_run_batch.return_value = [LatencyStats(label="local", success_rate=100.0)]
    args = Namespace(
        targets_file="t.yaml",
        output=None,
        pdf_dir=None,
        json=True,
        log_level="INFO",
        i_understand_authorized_target=False,
    )
    assert execute_batch(args, {}, use_rich=False) == 0


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_monitor_loop", new_callable=mock.AsyncMock)
@mock.patch("neural_blitz.cli.load_targets_file")
def test_execute_monitor(mock_load, mock_monitor):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": ".",
    }
    mock_monitor.return_value = None
    args = Namespace(
        targets_file="t.yaml",
        bind=None,
        http_port=None,
        interval=None,
        log_level="INFO",
        i_understand_authorized_target=False,
    )
    assert execute_monitor(args, {}, use_rich=False) == 0


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_test", new_callable=mock.AsyncMock)
def test_execute_test_with_sla(mock_run_test, tmp_path):
    sla = tmp_path / "sla.yaml"
    sla.write_text("min_success_rate: 50.0\n", encoding="utf-8")
    mock_run_test.return_value = LatencyStats(success_rate=100.0, count_received=10, count_sent=10)
    args = Namespace(
        host="127.0.0.1",
        port=9999,
        count=10,
        size=64,
        concurrency=1,
        timeout=1.0,
        rate=0.0,
        max_retries=0,
        warmup=0,
        no_co=False,
        no_progress=True,
        socket_rcvbuf=None,
        socket_sndbuf=None,
        metrics_output=None,
        json=True,
        log_level="INFO",
        label=None,
        sla=str(sla),
        fail_on_sla=False,
        pdf_report=None,
        i_understand_authorized_target=False,
        progress_interval=None,
    )
    assert execute_test(args, {}, use_rich=False) == 0
