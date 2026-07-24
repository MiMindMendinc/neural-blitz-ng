"""Tests for configuration loading and validation."""

import textwrap
from pathlib import Path

import pytest

from neural_blitz.config import (
    MonitorConfig,
    TestConfig,
    load_config,
    normalize_test_values,
    validate_config_file,
    validate_monitor_config,
    validate_test_config,
)
from neural_blitz.constants import HEADER_SIZE
from neural_blitz.errors import ConfigError


@pytest.mark.unit
def test_validate_test_config_accepts_valid_defaults():
    validate_test_config(TestConfig())


@pytest.mark.unit
def test_validate_test_config_rejects_invalid_port():
    with pytest.raises(ConfigError):
        validate_test_config(TestConfig(port=70000))


@pytest.mark.unit
def test_validate_test_config_rejects_too_small_packet():
    with pytest.raises(ConfigError):
        validate_test_config(TestConfig(size=HEADER_SIZE - 1))


@pytest.mark.unit
def test_validate_monitor_config_rejects_bad_interval():
    with pytest.raises(ConfigError):
        validate_monitor_config(MonitorConfig(interval=0))


@pytest.mark.unit
def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/neural_blitz.yaml")


@pytest.mark.unit
def test_validate_config_file_bad_yaml(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("targets: [not-a-mapping]\n  - oops\n", encoding="utf-8")
    errors = validate_config_file(str(bad))
    assert errors


@pytest.mark.unit
def test_validate_config_file_valid(tmp_path: Path):
    cfg = tmp_path / "ok.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            defaults:
              count: 100
            targets:
              - label: local
                host: 127.0.0.1
                port: 9999
            """
        ),
        encoding="utf-8",
    )
    errors = validate_config_file(str(cfg))
    assert errors == []


@pytest.mark.unit
def test_normalize_test_values_coerces_bool_strings():
    cfg = normalize_test_values(
        {
            "host": "127.0.0.1",
            "port": 9999,
            "count": 10,
            "size": 64,
            "concurrency": 1,
            "timeout": 1.0,
            "rate": 0,
            "max_retries": 0,
            "warmup": 0,
            "co_correction": "true",
            "progress_enabled": "false",
        }
    )
    assert cfg.co_correction is True
    assert cfg.progress_enabled is False


@pytest.mark.unit
def test_monitor_tls_requires_certificate_and_key():
    with pytest.raises(ConfigError, match="both"):
        validate_monitor_config(MonitorConfig(tls_cert_file="/tmp/cert.pem"))


@pytest.mark.unit
def test_validate_config_rejects_unknown_config_version(tmp_path: Path):
    cfg = tmp_path / "future.yaml"
    cfg.write_text("config_version: 2\n", encoding="utf-8")
    assert "config_version must be 1" in validate_config_file(str(cfg))


@pytest.mark.unit
def test_validate_config_validates_server_values(tmp_path: Path):
    cfg = tmp_path / "bad-server.yaml"
    cfg.write_text("server:\n  port: 70000\n", encoding="utf-8")
    errors = validate_config_file(str(cfg))
    assert any(error.startswith("server config: Port must") for error in errors)
