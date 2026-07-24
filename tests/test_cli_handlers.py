"""Direct CLI handler tests."""

from argparse import Namespace
from unittest import mock

import pytest

from neural_blitz.cli import (
    build_monitor_config,
    build_server_config,
    build_test_config,
    execute_compare,
    execute_server,
    execute_validate_config,
    execute_version,
)
from neural_blitz.metrics import LatencyStats, write_metrics


@pytest.mark.unit
def test_build_test_config_from_args():
    args = Namespace(
        host="127.0.0.1",
        port=9999,
        count=100,
        size=64,
        concurrency=5,
        timeout=1.0,
        rate=0.0,
        max_retries=0,
        warmup=0,
        no_co=False,
        no_progress=True,
        socket_rcvbuf=None,
        socket_sndbuf=None,
        metrics_output=None,
        json=False,
        log_level=None,
        label=None,
        sla=None,
        fail_on_sla=False,
        pdf_report=None,
        i_understand_authorized_target=False,
        progress_interval=None,
    )
    cfg = build_test_config(args, {})
    assert cfg.host == "127.0.0.1"
    assert cfg.progress_enabled is False


@pytest.mark.unit
def test_build_server_and_monitor_config():
    args = Namespace(bind=None, port=None, log_level=None, http_port=None, interval=None)
    server = build_server_config(
        args,
        {"server": {"port": 9998, "max_tracked_clients": 7, "client_state_ttl": 12, "cleanup_interval": 3}},
    )
    assert server.port == 9998
    assert (server.max_tracked_clients, server.client_state_ttl, server.cleanup_interval) == (7, 12.0, 3.0)
    monitor = build_monitor_config(args, {"monitor": {"http_port": 7777}})
    assert monitor.http_port == 7777


@pytest.mark.unit
def test_execute_version_json(capsys):
    args = Namespace(json=True)
    assert execute_version(args) == 0
    assert '"version"' in capsys.readouterr().out


@pytest.mark.unit
def test_execute_validate_config(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("targets:\n  - label: x\n    host: 127.0.0.1\n    port: 1\n", encoding="utf-8")
    args = Namespace(path=str(path), json=False)
    assert execute_validate_config(args) == 0


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_server", new_callable=mock.AsyncMock)
def test_execute_server(mock_run_server):
    args = Namespace(bind="127.0.0.1", port=9999, log_level="INFO")
    assert execute_server(args, {}, use_rich=False) == 0
    mock_run_server.assert_awaited_once()


@pytest.mark.unit
def test_execute_compare_with_output(tmp_path):
    base = tmp_path / "b.json"
    cand = tmp_path / "c.json"
    out = tmp_path / "out.json"
    write_metrics(LatencyStats(p95_us=10.0), str(base))
    write_metrics(LatencyStats(p95_us=11.0), str(cand))
    args = Namespace(
        baseline=str(base),
        candidate=str(cand),
        output=str(out),
        json=True,
        max_p95_regression=None,
        max_p99_regression=None,
        max_loss_regression=None,
        max_success_regression=None,
        fail_on_regression=False,
        log_level="INFO",
    )
    assert execute_compare(args, use_rich=False) == 0
    assert out.exists()
