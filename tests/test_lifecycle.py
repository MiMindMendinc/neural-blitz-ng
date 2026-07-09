"""run_monitor_loop and run_server lifecycle tests."""

import asyncio
from unittest import mock

import pytest

from neural_blitz.config import MonitorConfig
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
