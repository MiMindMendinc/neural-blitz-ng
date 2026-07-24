"""Regression checks for post-merge hardening behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from neural_blitz.config import ServerConfig, TestConfig, validate_server_config
from neural_blitz.errors import ConfigError, NeuralBlitzError
from neural_blitz.monitor import _atomic_json_write, _initialize_target_states
from neural_blitz.udp_client import resolve_hosts, run_test
from neural_blitz.udp_server import EchoServerProtocol


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tracked_clients": 0},
        {"client_state_ttl": 0},
        {"cleanup_interval": 0},
    ],
)
def test_server_client_state_bounds_are_validated(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigError):
        validate_server_config(ServerConfig(**kwargs))  # type: ignore[arg-type]


def test_atomic_monitor_state_write_is_valid_json(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    _atomic_json_write(str(destination), {"ok": True})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_monitor_initialization_rejects_duplicate_labels() -> None:
    with pytest.raises(ConfigError, match="unique"):
        _initialize_target_states(
            {},
            {"targets": [{"label": "same"}, {"label": "same"}]},
            {},
        )


def test_monitor_initialization_rejects_invalid_target() -> None:
    with pytest.raises(ConfigError, match="mapping"):
        _initialize_target_states({}, {"targets": ["invalid"]}, {})


def test_monitor_initialization_rejects_invalid_shared_overrides() -> None:
    with pytest.raises(ConfigError, match="test"):
        _initialize_target_states({}, {"test": "invalid", "targets": []}, {})


def test_unlimited_server_does_not_track_clients() -> None:
    protocol = EchoServerProtocol(rate_limit=0)
    assert protocol._clients == {}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tracked_clients": 0},
        {"client_state_ttl": 0},
        {"cleanup_interval": 0},
    ],
)
def test_server_constructor_rejects_invalid_client_state_options(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        EchoServerProtocol(**kwargs)  # type: ignore[arg-type]


def test_server_removes_expired_client_without_full_cleanup() -> None:
    now = [0.0]
    protocol = EchoServerProtocol(rate_limit=1, client_state_ttl=1, cleanup_interval=100, clock=lambda: now[0])
    assert protocol._allow("host")
    now[0] = 2.0
    assert protocol._allow("host")


def test_resolver_rejects_non_ip_udp_records(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket
    import neural_blitz.udp_client as udp_client

    monkeypatch.setattr(
        udp_client.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_UNIX, socket.SOCK_DGRAM, 0, "", "/tmp/socket")],
    )
    with pytest.raises(NeuralBlitzError, match="IPv4 or IPv6"):
        resolve_hosts("example", 9999)


def test_validate_config_reports_schema_load_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import neural_blitz.config as config_module

    config = tmp_path / "config.yaml"
    config.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_schema_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == "neural_blitz.schema.json":
            raise OSError("unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_schema_read)
    assert any(
        "Unable to load configuration schema" in error for error in config_module.validate_config_file(str(config))
    )


@pytest.mark.asyncio
async def test_client_reports_all_failed_resolved_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    import socket
    import neural_blitz.udp_client as client

    monkeypatch.setattr(
        client,
        "resolve_hosts",
        lambda *_: [(socket.AF_INET, ("127.0.0.1", 9999)), (socket.AF_INET, ("127.0.0.2", 9999))],
    )
    loop = asyncio.get_running_loop()
    with patch.object(loop, "create_datagram_endpoint", side_effect=OSError("blocked")):
        with pytest.raises(NeuralBlitzError, match="Unable to reach UDP host"):
            await run_test(TestConfig(host="127.0.0.1"))
