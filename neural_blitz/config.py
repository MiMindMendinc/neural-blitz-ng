"""YAML configuration loading, merging, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neural_blitz.constants import DEFAULT_CONFIG_BASENAME, HEADER_SIZE
from neural_blitz.errors import ConfigError, DependencyMissing
from neural_blitz.metrics import validate_metrics_output_path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class TestConfig:
    host: str = "127.0.0.1"
    port: int = 9999
    count: int = 1000
    size: int = 64
    concurrency: int = 50
    timeout: float = 2.0
    rate: float = 0.0
    max_retries: int = 0
    warmup: int = 50
    metrics_output: str = ""
    log_level: str = "INFO"
    socket_rcvbuf: int = 4_194_304
    socket_sndbuf: int = 4_194_304
    co_correction: bool = True
    progress_interval: float = 1.0
    progress_enabled: bool = True
    label: str = "candidate"
    sla_path: str = ""
    fail_on_sla: bool = False
    pdf_report: str = ""
    authorized_target: bool = False


@dataclass(frozen=True)
class ServerConfig:
    bind: str = "127.0.0.1"
    port: int = 9999
    log_level: str = "INFO"


@dataclass(frozen=True)
class MonitorConfig:
    bind: str = "0.0.0.0"
    http_port: int = 8888
    interval: int = 30
    history_limit: int = 100
    log_level: str = "INFO"


def ensure_yaml_available() -> None:
    if yaml is None:
        raise DependencyMissing("YAML support requires PyYAML. Install with: pip install pyyaml")


def read_yaml(path: Path) -> dict[str, Any]:
    ensure_yaml_available()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigError(f"Unable to read config file '{path}': {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Unable to parse YAML config '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file '{path}' must contain a top-level mapping")
    return data


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")
    return read_yaml(config_path)


def get_config_section(config_data: dict[str, Any], command: str) -> dict[str, Any]:
    defaults = config_data.get("defaults", {})
    section = config_data.get(command, {})
    if defaults and not isinstance(defaults, dict):
        raise ConfigError("Config key 'defaults' must be a mapping")
    if section and not isinstance(section, dict):
        raise ConfigError(f"Config section '{command}' must be a mapping")
    merged: dict[str, Any] = {}
    merged.update(defaults or {})
    merged.update(section or {})
    return merged


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"Invalid boolean value: {value!r}")


def default_test_values(config_data: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 9999,
        "count": 1000,
        "size": 64,
        "concurrency": 50,
        "timeout": 2.0,
        "rate": 0.0,
        "max_retries": 0,
        "warmup": 50,
        "metrics_output": "",
        "log_level": "INFO",
        "socket_rcvbuf": 4_194_304,
        "socket_sndbuf": 4_194_304,
        "progress_interval": 1.0,
        "label": "candidate",
        "sla_path": "",
        "fail_on_sla": False,
        "pdf_report": "",
        "progress_enabled": True,
        "co_correction": True,
        "authorized_target": False,
    }
    defaults.update(get_config_section(config_data, "test"))
    return defaults


def normalize_test_values(values: dict[str, Any]) -> TestConfig:
    return TestConfig(
        host=str(values["host"]),
        port=int(values["port"]),
        count=int(values["count"]),
        size=int(values["size"]),
        concurrency=int(values["concurrency"]),
        timeout=float(values["timeout"]),
        rate=float(values["rate"]),
        max_retries=int(values["max_retries"]),
        warmup=int(values["warmup"]),
        metrics_output=str(values.get("metrics_output", "")),
        log_level=str(values.get("log_level", "INFO")),
        socket_rcvbuf=int(values.get("socket_rcvbuf", 4_194_304)),
        socket_sndbuf=int(values.get("socket_sndbuf", 4_194_304)),
        co_correction=values["co_correction"]
        if isinstance(values["co_correction"], bool)
        else coerce_bool(values["co_correction"]),
        progress_interval=float(values.get("progress_interval", 1.0)),
        progress_enabled=values["progress_enabled"]
        if isinstance(values["progress_enabled"], bool)
        else coerce_bool(values["progress_enabled"]),
        label=str(values.get("label", "candidate")),
        sla_path=str(values.get("sla_path", "")),
        fail_on_sla=values.get("fail_on_sla", False)
        if isinstance(values.get("fail_on_sla"), bool)
        else coerce_bool(values.get("fail_on_sla", False)),
        pdf_report=str(values.get("pdf_report", "")),
        authorized_target=values.get("authorized_target", False)
        if isinstance(values.get("authorized_target"), bool)
        else coerce_bool(values.get("authorized_target", False)),
    )


def validate_test_config(config: TestConfig) -> None:
    if config.port <= 0 or config.port > 65535:
        raise ConfigError("Port must be between 1 and 65535")
    if config.count <= 0:
        raise ConfigError("Count must be greater than zero")
    if config.size < HEADER_SIZE:
        raise ConfigError(f"Packet size must be >= {HEADER_SIZE}")
    if config.concurrency <= 0:
        raise ConfigError("Concurrency must be greater than zero")
    if config.timeout <= 0:
        raise ConfigError("Timeout must be greater than zero")
    if config.rate < 0:
        raise ConfigError("Rate cannot be negative")
    if config.max_retries < 0:
        raise ConfigError("Max retries cannot be negative")
    if config.warmup < 0:
        raise ConfigError("Warmup cannot be negative")
    if config.socket_rcvbuf <= 0 or config.socket_sndbuf <= 0:
        raise ConfigError("Socket buffer sizes must be greater than zero")
    validate_metrics_output_path(config.metrics_output)
    if config.pdf_report and Path(config.pdf_report).suffix.lower() != ".pdf":
        raise ConfigError("PDF report output must use a .pdf extension")


def validate_server_config(config: ServerConfig) -> None:
    if config.port <= 0 or config.port > 65535:
        raise ConfigError("Port must be between 1 and 65535")


def validate_monitor_config(config: MonitorConfig) -> None:
    if config.http_port <= 0 or config.http_port > 65535:
        raise ConfigError("HTTP port must be between 1 and 65535")
    if config.interval <= 0:
        raise ConfigError("Monitor interval must be greater than zero")
    if config.history_limit <= 0:
        raise ConfigError("Monitor history_limit must be greater than zero")


def validate_config_file(path: str) -> list[str]:
    errors: list[str] = []
    try:
        data = load_config(path)
    except ConfigError as exc:
        return [str(exc)]
    for section in ("defaults", "test", "server", "monitor", "sla"):
        value = data.get(section)
        if value is not None and not isinstance(value, dict):
            errors.append(f"Section '{section}' must be a mapping")
    targets = data.get("targets")
    if targets is not None:
        if not isinstance(targets, list):
            errors.append("'targets' must be a list")
        else:
            for index, target in enumerate(targets):
                if not isinstance(target, dict):
                    errors.append(f"targets[{index}] must be a mapping")
                    continue
                if "host" not in target:
                    errors.append(f"targets[{index}] missing 'host'")
                port = target.get("port", 9999)
                if not isinstance(port, int) or port <= 0 or port > 65535:
                    errors.append(f"targets[{index}] invalid port: {port!r}")
    try:
        test_cfg = normalize_test_values(default_test_values(data))
        validate_test_config(test_cfg)
    except ConfigError as exc:
        errors.append(f"test config: {exc}")
    try:
        monitor_defaults: dict[str, Any] = {
            "bind": "0.0.0.0",
            "http_port": 8888,
            "interval": 30,
            "history_limit": 100,
            "log_level": "INFO",
        }
        monitor_defaults.update(get_config_section(data, "monitor"))
        validate_monitor_config(
            MonitorConfig(
                bind=str(monitor_defaults["bind"]),
                http_port=int(monitor_defaults["http_port"]),
                interval=int(monitor_defaults["interval"]),
                history_limit=int(monitor_defaults.get("history_limit", 100)),
                log_level=str(monitor_defaults["log_level"]),
            )
        )
    except (ConfigError, TypeError, KeyError) as exc:
        errors.append(f"monitor config: {exc}")
    return errors


def load_targets_file(path: str) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    raw = load_config(str(config_path))
    targets = raw.get("targets", [])
    if not isinstance(targets, list) or not targets:
        raise ConfigError("Targets file must include a non-empty 'targets' list")
    raw["__base_dir"] = str(config_path.parent)
    return raw


def build_test_config_from_overrides(config_data: dict[str, Any], overrides: dict[str, Any]) -> TestConfig:
    values = default_test_values(config_data)
    for key, value in overrides.items():
        if key in values and value is not None:
            values[key] = value
    return normalize_test_values(values)


def write_sample_config(path: str = DEFAULT_CONFIG_BASENAME) -> None:
    ensure_yaml_available()
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    sample = """# Neural Blitz NG example configuration
defaults:
  count: 1000
  size: 64
  concurrency: 50
  timeout: 2.0
  rate: 1000
  warmup: 50
  max_retries: 0
  co_correction: true

monitor:
  bind: "0.0.0.0"
  http_port: 8888
  interval: 30
  history_limit: 100

targets:
  - label: local
    host: 127.0.0.1
    port: 9999
    sla: examples/sla.yaml

server:
  bind: 127.0.0.1
  port: 9999
"""
    try:
        destination.write_text(sample, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Unable to write sample config '{destination}': {exc}") from exc
