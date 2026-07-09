"""Safety limits and authorized-use policy enforcement."""

from __future__ import annotations

import ipaddress
import logging
import os
import warnings
from dataclasses import dataclass

from neural_blitz.constants import (
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_COUNT,
    DEFAULT_MAX_PACKET_SIZE,
    DEFAULT_MAX_RATE,
    DEFAULT_MAX_TIMEOUT,
    DEFAULT_MIN_TIMEOUT,
    SAFE_TARGET_HOSTS,
)
from neural_blitz.errors import SafetyViolation

logger = logging.getLogger("neural_blitz")

RESPONSIBLE_USE_NOTICE = (
    "Neural Blitz NG is for authorized network monitoring and benchmarking only. "
    "Only test systems you own or have explicit permission to measure."
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SafetyViolation(f"Invalid integer for {name}: {raw!r}") from exc
    if value != default:
        warnings.warn(f"Safety ceiling {name} overridden to {value}", stacklevel=3)
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SafetyViolation(f"Invalid float for {name}: {raw!r}") from exc
    if value != default:
        warnings.warn(f"Safety ceiling {name} overridden to {value}", stacklevel=3)
    return value


@dataclass(frozen=True)
class SafetyLimits:
    max_count: int = DEFAULT_MAX_COUNT
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_rate: float = DEFAULT_MAX_RATE
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE
    min_timeout: float = DEFAULT_MIN_TIMEOUT
    max_timeout: float = DEFAULT_MAX_TIMEOUT

    @classmethod
    def from_env(cls) -> SafetyLimits:
        return cls(
            max_count=_env_int("NEURAL_BLITZ_MAX_COUNT", DEFAULT_MAX_COUNT),
            max_concurrency=_env_int("NEURAL_BLITZ_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY),
            max_rate=_env_float("NEURAL_BLITZ_MAX_RATE", DEFAULT_MAX_RATE),
            max_packet_size=_env_int("NEURAL_BLITZ_MAX_PACKET_SIZE", DEFAULT_MAX_PACKET_SIZE),
            min_timeout=_env_float("NEURAL_BLITZ_MIN_TIMEOUT", DEFAULT_MIN_TIMEOUT),
            max_timeout=_env_float("NEURAL_BLITZ_MAX_TIMEOUT", DEFAULT_MAX_TIMEOUT),
        )


def is_private_or_loopback(host: str) -> bool:
    if host.lower() in SAFE_TARGET_HOSTS:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def validate_test_safety(
    *,
    host: str,
    count: int,
    size: int,
    concurrency: int,
    timeout: float,
    rate: float,
    authorized_target: bool,
    limits: SafetyLimits | None = None,
) -> None:
    limits = limits or SafetyLimits.from_env()
    if count > limits.max_count:
        raise SafetyViolation(f"count {count} exceeds safety limit {limits.max_count}")
    if concurrency > limits.max_concurrency:
        raise SafetyViolation(f"concurrency {concurrency} exceeds safety limit {limits.max_concurrency}")
    if rate > limits.max_rate:
        raise SafetyViolation(f"rate {rate} exceeds safety limit {limits.max_rate}")
    if size > limits.max_packet_size:
        raise SafetyViolation(f"packet size {size} exceeds safety limit {limits.max_packet_size}")
    if timeout < limits.min_timeout or timeout > limits.max_timeout:
        raise SafetyViolation(f"timeout {timeout}s must be between {limits.min_timeout} and {limits.max_timeout}")
    if not authorized_target and not is_private_or_loopback(host):
        raise SafetyViolation(
            f"Target host '{host}' is not localhost/private. "
            "Use --i-understand-authorized-target only when you have explicit permission."
        )


def log_responsible_use_notice() -> None:
    logger.warning(RESPONSIBLE_USE_NOTICE)
