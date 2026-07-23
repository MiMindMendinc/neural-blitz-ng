"""run_monitor_loop and run_server lifecycle tests."""

import asyncio
import json
import signal
from pathlib import Path
from unittest import mock

import pytest

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
async def test_run_monitor_loop_rejects_missing_or_empty_auth_token(
    tmp_path: Path, contents: str | None, message: str
):
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
