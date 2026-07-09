"""SLA configuration loading and evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from neural_blitz.config import load_config
from neural_blitz.errors import ConfigError
from neural_blitz.metrics import LatencyStats


@dataclass(frozen=True)
class SLAConfig:
    min_success_rate: float | None = None
    max_loss_rate: float | None = None
    max_mean_us: float | None = None
    max_p95_us: float | None = None
    max_p99_us: float | None = None
    max_p999_us: float | None = None
    max_co_p99_us: float | None = None
    max_jitter_us: float | None = None
    min_pps: float | None = None


def load_sla(path: str) -> SLAConfig:
    raw = load_config(path)
    section = raw.get("sla", raw)
    if not isinstance(section, dict):
        raise ConfigError("SLA config must be a mapping")
    allowed = set(SLAConfig.__dataclass_fields__)
    filtered = {key: section[key] for key in section if key in allowed}
    return SLAConfig(**filtered)


def evaluate_sla(stats: LatencyStats, sla: SLAConfig) -> list[str]:
    failures: list[str] = []
    checks: list[tuple[str, str, float | None, float, Callable[[float, float], bool], str]] = [
        ("success_rate", "min", sla.min_success_rate, stats.success_rate, lambda a, lim: a >= lim, "%"),
        ("loss_rate", "max", sla.max_loss_rate, stats.loss_rate, lambda a, lim: a <= lim, "%"),
        ("mean_us", "max", sla.max_mean_us, stats.mean_us, lambda a, lim: a <= lim, "us"),
        ("p95_us", "max", sla.max_p95_us, stats.p95_us, lambda a, lim: a <= lim, "us"),
        ("p99_us", "max", sla.max_p99_us, stats.p99_us, lambda a, lim: a <= lim, "us"),
        ("p999_us", "max", sla.max_p999_us, stats.p999_us, lambda a, lim: a <= lim, "us"),
        ("co_p99_us", "max", sla.max_co_p99_us, stats.co_p99_us, lambda a, lim: a <= lim, "us"),
        ("jitter_us", "max", sla.max_jitter_us, stats.jitter_us, lambda a, lim: a <= lim, "us"),
        ("pps", "min", sla.min_pps, stats.pps, lambda a, lim: a >= lim, "pps"),
    ]
    for metric, bound, limit, actual, comparator, unit in checks:
        if limit is None:
            continue
        if not comparator(actual, limit):
            failures.append(f"{metric}: actual={actual:.3f}{unit} violates {bound}={limit:.3f}{unit}")
    return failures


def validate_sla_config(sla: SLAConfig) -> list[str]:
    errors: list[str] = []
    if sla.min_success_rate is not None and not (0 <= sla.min_success_rate <= 100):
        errors.append("min_success_rate must be between 0 and 100")
    if sla.max_loss_rate is not None and not (0 <= sla.max_loss_rate <= 100):
        errors.append("max_loss_rate must be between 0 and 100")
    for name in ("max_mean_us", "max_p95_us", "max_p99_us", "max_p999_us", "max_co_p99_us", "max_jitter_us"):
        value = getattr(sla, name)
        if value is not None and value < 0:
            errors.append(f"{name} must be non-negative")
    if sla.min_pps is not None and sla.min_pps < 0:
        errors.append("min_pps must be non-negative")
    return errors
