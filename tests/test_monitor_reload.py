"""Monitor config hot-reload helpers and lifecycle."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from neural_blitz.config import MonitorConfig
from neural_blitz.errors import ConfigError
from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import (
    MonitorRuntime,
    TargetState,
    apply_reloadable_monitor_settings,
    build_monitor_app,
    configured_target_labels,
    prune_unconfigured_targets,
    register_monitor_signal_handlers,
    reload_monitor_config,
    run_monitor_loop,
    targets_file_mtime,
)


def _runtime(**overrides: object) -> MonitorRuntime:
    values: dict[str, object] = {
        "interval": 30,
        "history_limit": 10,
        "stale_after_seconds": 60,
        "targets_data": {"targets": [{"label": "kept", "host": "127.0.0.1", "port": 9999}]},
    }
    values.update(overrides)
    return MonitorRuntime(**values)  # type: ignore[arg-type]


@pytest.mark.unit
def test_targets_file_mtime_returns_none_for_missing_path(tmp_path: Path):
    assert targets_file_mtime(str(tmp_path / "missing.yaml")) is None


@pytest.mark.unit
def test_configured_target_labels_skips_non_mapping_entries():
    labels = configured_target_labels(
        {
            "targets": [
                {"label": "named", "host": "127.0.0.1"},
                {"name": "legacy", "host": "127.0.0.1"},
                "bad",
                {"host": "127.0.0.1"},
            ]
        }
    )
    assert labels == {"named", "legacy", "target-4"}


@pytest.mark.unit
def test_prune_unconfigured_targets_drops_removed_labels():
    states = {"keep": TargetState(), "drop": TargetState()}
    latest = {"keep": LatencyStats(label="keep"), "drop": LatencyStats(label="drop")}
    history = {"keep": [{}], "drop": [{}]}
    removed = prune_unconfigured_targets({"keep"}, states, latest, history)
    assert removed == ["drop"]
    assert set(states) == {"keep"}
    assert set(latest) == {"keep"}
    assert set(history) == {"keep"}


@pytest.mark.unit
def test_apply_reloadable_monitor_settings_updates_runtime():
    runtime = _runtime()
    apply_reloadable_monitor_settings(
        {"monitor": {"interval": 15, "history_limit": 8, "stale_after_seconds": 90}},
        runtime,
    )
    assert (runtime.interval, runtime.history_limit, runtime.stale_after_seconds) == (15, 8, 90)


@pytest.mark.unit
def test_apply_reloadable_monitor_settings_accepts_missing_or_null_section():
    runtime = _runtime(interval=12)
    apply_reloadable_monitor_settings({}, runtime)
    apply_reloadable_monitor_settings({"monitor": None}, runtime)
    assert runtime.interval == 12


@pytest.mark.unit
@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"interval": 0}, "interval"),
        ({"history_limit": 0}, "history_limit"),
        ({"stale_after_seconds": 0}, "stale_after_seconds"),
        ("not-a-mapping", "must be a mapping"),
    ],
)
def test_apply_reloadable_monitor_settings_rejects_invalid_values(section: object, message: str):
    runtime = _runtime()
    with pytest.raises(ConfigError, match=message):
        apply_reloadable_monitor_settings({"monitor": section}, runtime)


@pytest.mark.unit
def test_reload_monitor_config_prunes_and_skips_unchanged_mtime(tmp_path: Path):
    path = tmp_path / "targets.yaml"
    path.write_text(
        "targets:\n  - label: kept\n    host: 127.0.0.1\n    port: 9999\nmonitor:\n  interval: 45\n",
        encoding="utf-8",
    )
    runtime = _runtime()
    states = {"kept": TargetState(), "gone": TargetState()}
    latest = {"gone": LatencyStats(label="gone")}
    history = {"gone": [{}]}

    assert reload_monitor_config({}, str(path), states, latest, history, runtime, force=True)
    assert set(states) == {"kept"}
    assert "gone" not in latest
    assert runtime.interval == 45
    assert runtime.reload_error is None
    assert runtime.reload_count == 1

    assert reload_monitor_config({}, str(path), states, latest, history, runtime, force=False) is False
    assert runtime.reload_count == 1
    assert reload_monitor_config({}, str(path), states, latest, history, runtime, force=True)
    assert runtime.reload_count == 2
    assert set(states) == {"kept"}


@pytest.mark.unit
def test_reload_monitor_config_keeps_last_good_on_invalid_file(tmp_path: Path):
    path = tmp_path / "targets.yaml"
    path.write_text("targets: []\n", encoding="utf-8")
    original = {"targets": [{"label": "kept", "host": "127.0.0.1", "port": 9999}]}
    runtime = _runtime(targets_data=original)
    states = {"kept": TargetState()}
    latest: dict[str, LatencyStats] = {}
    history: dict[str, list[dict[str, object]]] = {}

    assert reload_monitor_config({}, str(path), states, latest, history, runtime, force=True) is False
    assert runtime.reload_error is not None
    assert "non-empty" in runtime.reload_error
    assert runtime.targets_data is original
    assert "kept" in states


@pytest.mark.unit
def test_register_monitor_signal_handlers_registers_sighup():
    recorded: list[object] = []

    class Loop:
        def add_signal_handler(self, sig: object, _callback: object) -> None:
            recorded.append(sig)

    register_monitor_signal_handlers(
        Loop(),  # type: ignore[arg-type]
        lambda: None,
        lambda: None,
        signals_module=SimpleNamespace(SIGINT=2, SIGTERM=15, SIGHUP=1),
    )
    assert recorded == [2, 15, 1]


@pytest.mark.unit
def test_register_monitor_signal_handlers_without_sighup():
    recorded: list[object] = []

    class Loop:
        def add_signal_handler(self, sig: object, _callback: object) -> None:
            recorded.append(sig)

    register_monitor_signal_handlers(
        Loop(),  # type: ignore[arg-type]
        lambda: None,
        lambda: None,
        signals_module=SimpleNamespace(SIGINT=2, SIGTERM=15),
    )
    assert recorded == [2, 15]


@pytest.mark.unit
def test_register_monitor_signal_handlers_swallows_unsupported_sighup():
    class Loop:
        def add_signal_handler(self, sig: object, _callback: object) -> None:
            if sig in {2, 15}:
                raise NotImplementedError
            raise OSError("SIGHUP unsupported")

    register_monitor_signal_handlers(
        Loop(),  # type: ignore[arg-type]
        lambda: None,
        lambda: None,
        signals_module=SimpleNamespace(SIGINT=2, SIGTERM=15, SIGHUP=1),
    )


@pytest.mark.integration
async def test_monitor_health_includes_reload_status():
    runtime = _runtime(reload_error="bad yaml", last_reload_at="2026-08-16T00:00:00+00:00", reload_count=3)
    app = build_monitor_app({}, {}, states={"local": TargetState()}, runtime=runtime)
    async with TestClient(TestServer(app)) as client:
        payload = await (await client.get("/health")).json()
        assert payload["config_reload_error"] == "bad yaml"
        assert payload["config_last_reload_at"] == "2026-08-16T00:00:00+00:00"
        assert payload["config_reload_count"] == 3


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
async def test_monitor_hot_reload_on_sighup_and_file_change(mock_batch: mock.AsyncMock, tmp_path: Path):
    targets = tmp_path / "targets.yaml"
    targets.write_text(
        "targets:\n  - label: first\n    host: 127.0.0.1\n    port: 9999\n",
        encoding="utf-8",
    )
    config = MonitorConfig(bind="127.0.0.1", http_port=0, interval=1)
    loop = asyncio.get_running_loop()
    handlers: dict[object, object] = {}
    captured: dict[str, object] = {}
    original_register = register_monitor_signal_handlers

    def capture(sig: object, callback: object) -> None:
        handlers[sig] = callback

    def capture_register(
        event_loop: object,
        on_signal: object,
        on_reload: object,
        *,
        signals_module: object = signal,
    ) -> None:
        captured["reload"] = on_reload
        original_register(event_loop, on_signal, on_reload, signals_module=signals_module)  # type: ignore[arg-type]

    async def after_first_cycle(*args: object, **kwargs: object):
        targets.write_text(
            "targets:\n  - label: second\n    host: 127.0.0.1\n    port: 9998\nmonitor:\n  interval: 15\n",
            encoding="utf-8",
        )
        captured["reload"]()  # type: ignore[operator]

        async def stop_second(*_args: object, **_kwargs: object):
            handlers[signal.SIGTERM]()  # type: ignore[operator]
            return [LatencyStats(label="second", success_rate=100.0)]

        mock_batch.side_effect = stop_second
        return [LatencyStats(label="first", success_rate=100.0)]

    mock_batch.side_effect = after_first_cycle
    with (
        mock.patch.object(loop, "add_signal_handler", side_effect=capture),
        mock.patch("neural_blitz.monitor.register_monitor_signal_handlers", side_effect=capture_register),
    ):
        await asyncio.wait_for(run_monitor_loop({}, str(targets), config), timeout=5.0)

    assert mock_batch.await_count == 2
    second_targets = mock_batch.await_args_list[1].args[1]["targets"]
    assert second_targets[0]["label"] == "second"


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_batch_tests")
@mock.patch("neural_blitz.monitor.load_targets_file")
async def test_monitor_no_reload_skips_later_loads(mock_load: mock.Mock, mock_batch: mock.AsyncMock):
    mock_load.return_value = {
        "targets": [{"label": "local", "host": "127.0.0.1", "port": 9999}],
        "__base_dir": ".",
    }
    calls = 0
    loop = asyncio.get_running_loop()
    handlers: dict[object, object] = {}

    def capture(sig: object, callback: object) -> None:
        handlers[sig] = callback

    async def run_cycles(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [LatencyStats(label="local", success_rate=100.0)]
        handlers[signal.SIGTERM]()  # type: ignore[operator]
        return [LatencyStats(label="local", success_rate=100.0)]

    async def time_out_wait(*args: object, **kwargs: object):
        args[0].close()
        raise asyncio.TimeoutError

    mock_batch.side_effect = run_cycles
    with (
        mock.patch.object(loop, "add_signal_handler", side_effect=capture),
        mock.patch("neural_blitz.monitor.asyncio.wait_for", side_effect=time_out_wait),
    ):
        await run_monitor_loop(
            {},
            "targets.yaml",
            MonitorConfig(bind="127.0.0.1", http_port=0, history_limit=1),
            reload_config=False,
        )

    assert mock_load.call_count == 1
    assert calls == 2
