"""run_monitor_loop and run_server lifecycle tests."""

import asyncio
import builtins
import json
import signal
from pathlib import Path
from unittest import mock

import pytest

import neural_blitz.monitor as monitor
from neural_blitz.config import MonitorConfig
from neural_blitz.errors import DependencyMissing
from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import run_monitor_loop
from neural_blitz.udp_server import run_server


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_run_monitor_loop_one_cycle(mock_load, mock_batch):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": ".",
    }
    mock_batch.return_value = [LatencyStats(label="local", success_rate=100.0)]

    config = MonitorConfig(bind="127.0.0.1", http_port=0, interval=60)
    task = asyncio.create_task(run_monitor_loop({}, "targets.yaml", config))

    await asyncio.sleep(0.3)

    # discover bound port from mock_batch being called
    assert mock_batch.called

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.integration
async def test_run_server_signal_shutdown():
    loop = asyncio.get_running_loop()
    handlers: dict[int, object] = {}

    def capture(sig, cb):
        handlers[sig] = cb

    with mock.patch.object(loop, "add_signal_handler", side_effect=capture):
        task = asyncio.create_task(run_server("127.0.0.1", 0))
        await asyncio.sleep(0.05)
        for cb in handlers.values():
            cb()  # type: ignore[operator]
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("contents", "message"),
    [(None, "Unable to read monitor auth token file"), (" \n", "Monitor auth token file is empty")],
)
async def test_run_monitor_loop_rejects_missing_or_empty_auth_token(tmp_path: Path, contents: str | None, message: str):
    token_file = tmp_path / "monitor.token"
    if contents is not None:
        token_file.write_text(contents, encoding="utf-8")

    config = MonitorConfig(auth_token_file=str(token_file))

    with pytest.raises(DependencyMissing, match=message):
        await run_monitor_loop({}, "targets.yaml", config)


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_monitor_cycle_writes_state_and_shuts_down_on_signal(mock_load, mock_batch, tmp_path: Path):
    mock_load.return_value = {
        "targets": [
            {"label": "working", "host": "127.0.0.1", "port": 9999},
            {"label": "broken", "host": "127.0.0.1", "port": 9998},
        ],
        "__base_dir": str(tmp_path),
    }
    mock_batch.return_value = [LatencyStats(label="working", success_rate=100.0)]
    state_file = tmp_path / "state" / "monitor.json"
    config = MonitorConfig(bind="127.0.0.1", http_port=0, interval=60, state_file=str(state_file))
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, object] = {}

    def capture(sig: signal.Signals, callback: object) -> None:
        handlers[sig] = callback

    async def stop_after_first_cycle(*args, **kwargs):
        kwargs["failures"]["broken"] = "connection refused"
        callback = handlers[signal.SIGTERM]
        callback()  # type: ignore[operator]
        return mock_batch.return_value

    mock_batch.side_effect = stop_after_first_cycle
    with mock.patch.object(loop, "add_signal_handler", side_effect=capture):
        await asyncio.wait_for(run_monitor_loop({}, "targets.yaml", config), timeout=2.0)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["targets"]["working"]["status"] == "ok"
    assert state["targets"]["working"]["latest"]["label"] == "working"
    assert state["targets"]["broken"]["status"] == "failed"
    assert state["targets"]["broken"]["last_error"] == "connection refused"
    assert state["targets"]["broken"]["consecutive_failures"] == 1
    assert mock_batch.await_count == 1


@pytest.mark.unit
async def test_run_monitor_loop_reports_missing_aiohttp(monkeypatch: pytest.MonkeyPatch):
    original_import = builtins.__import__

    def reject_aiohttp(name, *args, **kwargs):
        if name == "aiohttp":
            raise ImportError("aiohttp unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_aiohttp)

    with pytest.raises(DependencyMissing, match="Monitor mode requires aiohttp"):
        await run_monitor_loop({}, "targets.yaml", MonitorConfig())


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_monitor_uses_auth_token_and_tls_context(mock_load, mock_batch, tmp_path: Path):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": str(tmp_path),
    }
    mock_batch.return_value = [LatencyStats(label="local", success_rate=100.0)]
    token_file = tmp_path / "monitor.token"
    token_file.write_text("token-value\n", encoding="utf-8")
    config = MonitorConfig(
        bind="127.0.0.1",
        http_port=0,
        auth_token_file=str(token_file),
        tls_cert_file="cert.pem",
        tls_key_file="key.pem",
    )
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, object] = {}
    ssl_context = mock.Mock()
    site = mock.Mock()
    site.start = mock.AsyncMock()

    def capture(sig: signal.Signals, callback: object) -> None:
        handlers[sig] = callback

    async def stop_after_cycle(*args, **kwargs):
        handlers[signal.SIGTERM]()  # type: ignore[operator]
        return mock_batch.return_value

    mock_batch.side_effect = stop_after_cycle
    with (
        mock.patch.object(loop, "add_signal_handler", side_effect=capture),
        mock.patch("neural_blitz.monitor.ssl.create_default_context", return_value=ssl_context),
        mock.patch("aiohttp.web.TCPSite", return_value=site) as tcpsite,
    ):
        await run_monitor_loop({}, "targets.yaml", config)

    ssl_context.load_cert_chain.assert_called_once_with("cert.pem", "key.pem")
    assert tcpsite.call_args.kwargs["ssl_context"] is ssl_context


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_monitor_trims_history_and_exits_after_timeout_shutdown(mock_load, mock_batch):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": ".",
    }
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, object] = {}
    calls = 0

    def capture(sig: signal.Signals, callback: object) -> None:
        handlers[sig] = callback

    async def run_cycles(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            handlers[signal.SIGTERM]()  # type: ignore[operator]
        return [LatencyStats(label="local", success_rate=100.0, count_sent=calls)]

    async def time_out_wait(*args, **kwargs):
        args[0].close()
        raise asyncio.TimeoutError

    mock_batch.side_effect = run_cycles
    with (
        mock.patch.object(loop, "add_signal_handler", side_effect=capture),
        mock.patch("neural_blitz.monitor.asyncio.wait_for", side_effect=time_out_wait),
        mock.patch("neural_blitz.monitor.build_monitor_app", wraps=monitor.build_monitor_app) as build_app,
    ):
        await run_monitor_loop({}, "targets.yaml", MonitorConfig(bind="127.0.0.1", http_port=0, history_limit=1))

    history = build_app.call_args.args[1]
    assert calls == 2
    assert len(history["local"]) == 1
    assert history["local"][0]["count_sent"] == 2


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests", side_effect=RuntimeError("cycle exploded"))
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_monitor_logs_cycle_errors_and_still_shuts_down(mock_load, mock_batch):
    mock_load.return_value = {"targets": [], "__base_dir": "."}
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, object] = {}

    def capture(sig: signal.Signals, callback: object) -> None:
        handlers[sig] = callback

    async def stop_wait(*args, **kwargs):
        args[0].close()
        handlers[signal.SIGTERM]()  # type: ignore[operator]

    with (
        mock.patch.object(loop, "add_signal_handler", side_effect=capture),
        mock.patch("neural_blitz.monitor.asyncio.wait_for", side_effect=stop_wait),
    ):
        await run_monitor_loop({}, "targets.yaml", MonitorConfig(bind="127.0.0.1", http_port=0))

    mock_batch.assert_awaited_once()
