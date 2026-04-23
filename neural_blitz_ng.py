#!/usr/bin/env python3
"""Neural Blitz NG - production-ready UDP latency tester.

Preserves the original Neural Blitz v6 feature set while adding:
- Rich CLI output and progress bars
- YAML configuration support
- SLA validation
- Metrics comparison mode
- pip-ready packaging support
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import math
import os
import signal
import socket
import statistics
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - handled at runtime
    yaml = None

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table as PdfTable, TableStyle

    PDF_REPORTS_AVAILABLE = True
except ImportError:  # pragma: no cover - handled at runtime
    colors = None  # type: ignore[assignment]
    letter = None  # type: ignore[assignment]
    ParagraphStyle = None  # type: ignore[assignment]
    getSampleStyleSheet = None  # type: ignore[assignment]
    inch = None  # type: ignore[assignment]
    Paragraph = None  # type: ignore[assignment]
    SimpleDocTemplate = None  # type: ignore[assignment]
    Spacer = None  # type: ignore[assignment]
    PdfTable = None  # type: ignore[assignment]
    TableStyle = None  # type: ignore[assignment]
    PDF_REPORTS_AVAILABLE = False

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - handled at runtime
    RICH_AVAILABLE = False
    Console = None  # type: ignore[assignment]
    RichHandler = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Progress = None  # type: ignore[assignment]
    SpinnerColumn = None  # type: ignore[assignment]
    TextColumn = None  # type: ignore[assignment]
    BarColumn = None  # type: ignore[assignment]
    TaskProgressColumn = None  # type: ignore[assignment]
    TimeElapsedColumn = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]

__version__ = "8.0.0"
APP_NAME = "neural-blitz"
USE_RICH_OUTPUT = RICH_AVAILABLE

logger = logging.getLogger("neural_blitz")
console = Console(stderr=False) if RICH_AVAILABLE else None
error_console = Console(stderr=True) if RICH_AVAILABLE else None

_UVLOOP_AVAILABLE = False
try:
    import uvloop

    _UVLOOP_AVAILABLE = True
except ImportError:
    pass

HEADER_SIZE = 24
HEADER_STRUCT = struct.Struct("!Qqq")
DEFAULT_CONFIG_BASENAME = "neural_blitz.yaml"
SUPPORTED_METRICS_SUFFIXES = {".json", ".csv"}
EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_SLA_FAILURE = 2
EXIT_CONFIG_ERROR = 3
EXIT_COMPARISON_FAILURE = 4


class NeuralBlitzError(Exception):
    """Base application error."""


class ConfigError(NeuralBlitzError):
    """Raised when configuration is invalid."""


class MetricsError(NeuralBlitzError):
    """Raised when metrics files cannot be read or written."""


class SLAFailure(NeuralBlitzError):
    """Raised when SLA checks fail."""


def install_event_loop_policy() -> str:
    """Install uvloop if available. Returns loop engine name."""
    if _UVLOOP_AVAILABLE and os.environ.get("NEURAL_BLITZ_NO_UVLOOP") != "1":
        uvloop.install()
        return "uvloop"
    return "asyncio"


def build_packet(seq_id: int, size: int, scheduled_ns: int = 0) -> bytes:
    ts = time.monotonic_ns()
    header = HEADER_STRUCT.pack(seq_id, ts, scheduled_ns or ts)
    return header + b"\x00" * max(0, size - HEADER_SIZE)


def parse_packet(data: bytes) -> tuple[int, int, int]:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Packet too small: {len(data)} < {HEADER_SIZE}")
    return HEADER_STRUCT.unpack_from(data)


class LatencyRecorder:
    """Bucketed histogram recorder with optional CO-corrected counts."""

    __slots__ = ("_counts", "_total", "_min", "_max", "_sum", "_sum_sq", "_co_counts", "_co_total")

    _PRECISION = 3
    _MIN_VALUE = 1
    _MAX_VALUE = 3_600_000_000
    _BUCKET_COUNT = int(math.log2(_MAX_VALUE / _MIN_VALUE) * _PRECISION) + 2

    def __init__(self) -> None:
        self._counts = [0] * self._BUCKET_COUNT
        self._total = 0
        self._min = float("inf")
        self._max = 0.0
        self._sum = 0.0
        self._sum_sq = 0.0
        self._co_counts = [0] * self._BUCKET_COUNT
        self._co_total = 0

    def _bucket_for(self, value_us: float) -> int:
        if value_us <= self._MIN_VALUE:
            return 0
        if value_us >= self._MAX_VALUE:
            return self._BUCKET_COUNT - 1
        return min(int(math.log2(value_us / self._MIN_VALUE) * self._PRECISION), self._BUCKET_COUNT - 1)

    def _value_for(self, bucket: int) -> float:
        return self._MIN_VALUE * (2.0 ** (bucket / self._PRECISION))

    def record(self, value_us: float) -> None:
        bucket = self._bucket_for(value_us)
        self._counts[bucket] += 1
        self._total += 1
        self._min = min(self._min, value_us)
        self._max = max(self._max, value_us)
        self._sum += value_us
        self._sum_sq += value_us * value_us

    def record_corrected(self, value_us: float, expected_interval_us: float) -> None:
        self.record(value_us)
        bucket = self._bucket_for(value_us)
        self._co_counts[bucket] += 1
        self._co_total += 1
        if expected_interval_us <= 0 or value_us <= expected_interval_us:
            return
        missing = value_us - expected_interval_us
        while missing >= expected_interval_us:
            missing_bucket = self._bucket_for(missing)
            self._co_counts[missing_bucket] += 1
            self._co_total += 1
            missing -= expected_interval_us

    def percentile(self, percentile: float, corrected: bool = False) -> float:
        counts = self._co_counts if corrected else self._counts
        total = self._co_total if corrected else self._total
        if total == 0:
            return 0.0
        target = (percentile / 100.0) * total
        cumulative = 0
        for index, count in enumerate(counts):
            cumulative += count
            if cumulative >= target:
                return self._value_for(index)
        return self._value_for(self._BUCKET_COUNT - 1)

    @property
    def count(self) -> int:
        return self._total

    @property
    def mean(self) -> float:
        return self._sum / self._total if self._total else 0.0

    @property
    def stddev(self) -> float:
        if self._total < 2:
            return 0.0
        variance = (self._sum_sq / self._total) - (self.mean**2)
        return math.sqrt(max(0.0, variance))

    @property
    def min_val(self) -> float:
        return self._min if self._total else 0.0

    @property
    def max_val(self) -> float:
        return self._max


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


@dataclass(frozen=True)
class ServerConfig:
    bind: str = "0.0.0.0"
    port: int = 9999
    log_level: str = "INFO"


@dataclass(frozen=True)
class MonitorConfig:
    bind: str = "0.0.0.0"
    http_port: int = 8888
    interval: int = 30
    log_level: str = "INFO"


@dataclass(frozen=True)
class SLAConfig:
    min_success_rate: Optional[float] = None
    max_mean_us: Optional[float] = None
    max_p95_us: Optional[float] = None
    max_p99_us: Optional[float] = None
    max_p999_us: Optional[float] = None
    max_co_p99_us: Optional[float] = None
    max_jitter_us: Optional[float] = None
    min_pps: Optional[float] = None


@dataclass
class LatencyStats:
    count_sent: int = 0
    count_received: int = 0
    count_lost: int = 0
    count_retried: int = 0
    success_rate: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    mean_us: float = 0.0
    stddev_us: float = 0.0
    p50_us: float = 0.0
    p90_us: float = 0.0
    p95_us: float = 0.0
    p99_us: float = 0.0
    p999_us: float = 0.0
    p9999_us: float = 0.0
    co_p50_us: float = 0.0
    co_p99_us: float = 0.0
    co_p999_us: float = 0.0
    jitter_us: float = 0.0
    duration_s: float = 0.0
    pps: float = 0.0
    loop_engine: str = "asyncio"
    label: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return {key: round(value, 3) if isinstance(value, float) else value for key, value in asdict(self).items()}

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "LatencyStats":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {key: raw[key] for key in raw if key in allowed}
        return cls(**filtered)


def compute_stats(
    recorder: LatencyRecorder,
    raw_rtts: list[float],
    count_sent: int,
    count_retried: int,
    duration_s: float,
    loop_engine: str,
    label: str,
) -> LatencyStats:
    stats = LatencyStats(
        count_sent=count_sent,
        count_received=recorder.count,
        count_lost=count_sent - recorder.count,
        count_retried=count_retried,
        duration_s=duration_s,
        pps=count_sent / duration_s if duration_s > 0 else 0.0,
        loop_engine=loop_engine,
        label=label,
    )
    if recorder.count == 0:
        return stats
    stats.success_rate = recorder.count / count_sent * 100.0 if count_sent else 0.0
    stats.min_us = recorder.min_val
    stats.max_us = recorder.max_val
    stats.mean_us = recorder.mean
    stats.stddev_us = recorder.stddev
    stats.p50_us = recorder.percentile(50)
    stats.p90_us = recorder.percentile(90)
    stats.p95_us = recorder.percentile(95)
    stats.p99_us = recorder.percentile(99)
    stats.p999_us = recorder.percentile(99.9)
    stats.p9999_us = recorder.percentile(99.99)
    stats.co_p50_us = recorder.percentile(50, corrected=True)
    stats.co_p99_us = recorder.percentile(99, corrected=True)
    stats.co_p999_us = recorder.percentile(99.9, corrected=True)
    if len(raw_rtts) > 1:
        sorted_rtts = sorted(raw_rtts)
        stats.jitter_us = statistics.mean(
            abs(sorted_rtts[index + 1] - sorted_rtts[index]) for index in range(len(sorted_rtts) - 1)
        )
    return stats


class EchoServerProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.packet_count = 0

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport
        sock = transport.get_extra_info("socket")
        if sock is not None and hasattr(sock, "setsockopt"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4_194_304)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4_194_304)
            except OSError:
                logger.debug("Socket buffer tuning for server failed", exc_info=True)
        logger.info("Echo server listening on %s", transport.get_extra_info("sockname"))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        self.packet_count += 1
        self.transport.sendto(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Echo server socket error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.error("Echo server connection lost: %s", exc)
        logger.info("Echo server shut down after %d packets", self.packet_count)


class BlitzClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, rcvbuf: int = 4_194_304, sndbuf: int = 4_194_304) -> None:
        self.transport: Optional[asyncio.DatagramTransport] = None
        self._inflight: dict[int, asyncio.Future[tuple[float, int]]] = {}
        self._rcvbuf = rcvbuf
        self._sndbuf = sndbuf

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport
        sock = transport.get_extra_info("socket")
        if sock is not None and hasattr(sock, "setsockopt"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._rcvbuf)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self._sndbuf)
            except OSError as exc:
                logger.debug("Socket buffer tuning failed: %s", exc)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        recv_ns = time.monotonic_ns()
        try:
            seq_id, send_ns, sched_ns = parse_packet(data)
        except ValueError as exc:
            logger.debug("Malformed packet from %s: %s", addr, exc)
            return
        future = self._inflight.get(seq_id)
        if future is None or future.done():
            return
        rtt_us = (recv_ns - send_ns) / 1_000.0
        future.set_result((rtt_us, sched_ns))

    def error_received(self, exc: Exception) -> None:
        logger.error("Client socket error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.error("Client connection lost: %s", exc)
        for future in self._inflight.values():
            if not future.done():
                future.cancel()
        self._inflight.clear()

    def register(self, seq_id: int, future: asyncio.Future[tuple[float, int]]) -> None:
        self._inflight[seq_id] = future

    def unregister(self, seq_id: int) -> None:
        self._inflight.pop(seq_id, None)


class TokenBucketLimiter:
    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._tokens = 0.0
        self._max_tokens = max(1.0, rate * 0.1)
        self._last = time.monotonic()
        self._interval_us = (1_000_000.0 / rate) if rate > 0 else 0.0
        self._next_scheduled_ns = time.monotonic_ns()

    @property
    def expected_interval_us(self) -> float:
        return self._interval_us

    async def acquire(self) -> int:
        scheduled = self._next_scheduled_ns
        if self._rate <= 0:
            return time.monotonic_ns()
        self._next_scheduled_ns += int(self._interval_us * 1000)
        while True:
            now = time.monotonic()
            self._tokens = min(self._max_tokens, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return scheduled
            await asyncio.sleep((1.0 - self._tokens) / self._rate)


class ProgressReporter:
    """Rich progress with plain stderr fallback."""

    def __init__(self, total: int, enabled: bool) -> None:
        self._total = total
        self._enabled = enabled
        self._done = 0
        self._received = 0
        self._start = time.monotonic()
        self._progress = None
        self._task_id = None
        if enabled and USE_RICH_OUTPUT and RICH_AVAILABLE:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("{task.fields[recv]}/{task.fields[expected]} recv"),
                transient=True,
                console=error_console,
            )

    def __enter__(self) -> "ProgressReporter":
        if self._progress is not None:
            self._progress.start()
            self._task_id = self._progress.add_task("UDP latency test", total=self._total, recv=0, expected=self._total)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._progress is not None:
            self._progress.stop()
        elif self._enabled:
            print("", file=sys.stderr)

    def update(self, received: bool) -> None:
        self._done += 1
        if received:
            self._received += 1
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, advance=1, recv=self._received, expected=self._total)
        elif self._enabled:
            elapsed = max(time.monotonic() - self._start, 0.001)
            rate = self._done / elapsed
            pct = self._done / self._total * 100 if self._total else 100.0
            print(
                f"\r  > {self._done}/{self._total} ({pct:.0f}%) recv={self._received} rate={rate:.0f}/s",
                end="",
                file=sys.stderr,
                flush=True,
            )


def resolve_host(host: str, port: int) -> tuple[str, int]:
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as exc:
        raise NeuralBlitzError(f"Unable to resolve host '{host}': {exc}") from exc
    return host, port


async def send_one(
    protocol: BlitzClientProtocol,
    addr: tuple[str, int],
    seq_id: int,
    size: int,
    timeout: float,
    max_retries: int,
    limiter: TokenBucketLimiter,
) -> tuple[int, Optional[float], int, int]:
    loop = asyncio.get_running_loop()
    retries = 0
    for attempt in range(1 + max_retries):
        scheduled_ns = await limiter.acquire()
        future: asyncio.Future[tuple[float, int]] = loop.create_future()
        protocol.register(seq_id, future)
        if protocol.transport is None:
            protocol.unregister(seq_id)
            return seq_id, None, retries, scheduled_ns
        protocol.transport.sendto(build_packet(seq_id, size, scheduled_ns), addr)
        try:
            rtt_us, _ = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            return seq_id, rtt_us, retries, scheduled_ns
        except asyncio.TimeoutError:
            if not future.done():
                future.cancel()
            protocol.unregister(seq_id)
            if attempt < max_retries:
                retries += 1
                logger.debug("seq %d timeout, retry %d/%d", seq_id, retries, max_retries)
            else:
                return seq_id, None, retries, scheduled_ns
        except asyncio.CancelledError:
            protocol.unregister(seq_id)
            return seq_id, None, retries, scheduled_ns
        finally:
            protocol.unregister(seq_id)
    return seq_id, None, retries, 0


async def run_test(config: TestConfig) -> LatencyStats:
    loop = asyncio.get_running_loop()
    loop_engine = "uvloop" if _UVLOOP_AVAILABLE and type(loop).__module__.startswith("uvloop") else "asyncio"
    addr = resolve_host(config.host, config.port)

    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: BlitzClientProtocol(config.socket_rcvbuf, config.socket_sndbuf),
            local_addr=("0.0.0.0", 0),
        )
    except OSError as exc:
        raise NeuralBlitzError(f"Unable to create UDP client endpoint: {exc}") from exc

    limiter = TokenBucketLimiter(config.rate)
    logger.info(
        "Starting test label=%s count=%d size=%d host=%s port=%d concurrency=%d timeout=%.2fs rate=%s retries=%d warmup=%d co=%s engine=%s",
        config.label,
        config.count,
        config.size,
        config.host,
        config.port,
        config.concurrency,
        config.timeout,
        f"{config.rate:.0f}/s" if config.rate > 0 else "unlimited",
        config.max_retries,
        config.warmup,
        "on" if config.co_correction else "off",
        loop_engine,
    )

    try:
        if config.warmup > 0:
            logger.info("Warmup phase: %d packets", config.warmup)
            warmup_sem = asyncio.Semaphore(min(config.concurrency, config.warmup))
            warmup_limiter = TokenBucketLimiter(config.rate)

            async def warmup_send(seq: int) -> None:
                async with warmup_sem:
                    await send_one(protocol, addr, seq, config.size, config.timeout, 0, warmup_limiter)

            async with asyncio.TaskGroup() as task_group:
                for index in range(config.count, config.count + config.warmup):
                    task_group.create_task(warmup_send(index))

        recorder = LatencyRecorder()
        raw_rtts: list[float] = []
        total_retries = 0
        sem = asyncio.Semaphore(config.concurrency)
        expected_interval_us = limiter.expected_interval_us

        async def bounded(seq: int, progress: ProgressReporter) -> None:
            nonlocal total_retries
            async with sem:
                _, rtt, retries, _ = await send_one(
                    protocol,
                    addr,
                    seq,
                    config.size,
                    config.timeout,
                    config.max_retries,
                    limiter,
                )
                total_retries += retries
                if rtt is not None:
                    raw_rtts.append(rtt)
                    if config.co_correction and expected_interval_us > 0:
                        recorder.record_corrected(rtt, expected_interval_us)
                    else:
                        recorder.record(rtt)
                    progress.update(True)
                else:
                    progress.update(False)

        t0 = time.monotonic()
        with ProgressReporter(config.count, config.progress_enabled) as progress:
            async with asyncio.TaskGroup() as task_group:
                for index in range(config.count):
                    task_group.create_task(bounded(index, progress))

        duration = time.monotonic() - t0
    finally:
        transport.close()

    stats = compute_stats(recorder, raw_rtts, config.count, total_retries, duration, loop_engine, config.label)
    logger.info(
        "Done: %d/%d (%.1f%%) in %.2fs | min=%.1f p50=%.1f p95=%.1f p99=%.1f p99.9=%.1f max=%.1f us | co-p99=%.1f co-p99.9=%.1f | jitter=%.1f us pps=%.0f engine=%s",
        stats.count_received,
        stats.count_sent,
        stats.success_rate,
        stats.duration_s,
        stats.min_us,
        stats.p50_us,
        stats.p95_us,
        stats.p99_us,
        stats.p999_us,
        stats.max_us,
        stats.co_p99_us,
        stats.co_p999_us,
        stats.jitter_us,
        stats.pps,
        stats.loop_engine,
    )
    return stats


async def run_server(bind: str, port: int) -> None:
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(EchoServerProtocol, local_addr=(bind, port))
    except OSError as exc:
        raise NeuralBlitzError(f"Unable to start UDP echo server on {bind}:{port}: {exc}") from exc
    stop: asyncio.Future[None] = loop.create_future()

    def on_signal() -> None:
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, on_signal)
        except NotImplementedError:
            logger.debug("Signal handlers not supported on this platform")

    logger.info("Echo server on %s:%d - Ctrl+C to stop", bind, port)
    try:
        await stop
    except asyncio.CancelledError:
        logger.debug("Server cancelled")
    finally:
        transport.close()


def ensure_yaml_available() -> None:
    if yaml is None:
        raise ConfigError("YAML support requires PyYAML. Install with: pip install pyyaml")


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


def load_config(path: Optional[str]) -> dict[str, Any]:
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


def normalize_test_values(values: dict[str, Any]) -> TestConfig:
    return TestConfig(
        host=values["host"],
        port=values["port"],
        count=values["count"],
        size=values["size"],
        concurrency=values["concurrency"],
        timeout=values["timeout"],
        rate=values["rate"],
        max_retries=values["max_retries"],
        warmup=values["warmup"],
        metrics_output=values["metrics_output"],
        log_level=values["log_level"],
        socket_rcvbuf=values["socket_rcvbuf"],
        socket_sndbuf=values["socket_sndbuf"],
        co_correction=values["co_correction"] if isinstance(values["co_correction"], bool) else coerce_bool(values["co_correction"]),
        progress_interval=values["progress_interval"],
        progress_enabled=values["progress_enabled"] if isinstance(values["progress_enabled"], bool) else coerce_bool(values["progress_enabled"]),
        label=values["label"],
        sla_path=values["sla_path"],
        fail_on_sla=values["fail_on_sla"] if isinstance(values["fail_on_sla"], bool) else coerce_bool(values["fail_on_sla"]),
        pdf_report=values["pdf_report"],
    )


def default_test_values(config_data: dict[str, Any]) -> dict[str, Any]:
    defaults = {
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
    }
    defaults.update(get_config_section(config_data, "test"))
    return defaults


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
    if config.metrics_output:
        suffix = Path(config.metrics_output).suffix.lower()
        if suffix and suffix not in SUPPORTED_METRICS_SUFFIXES:
            raise ConfigError("Metrics output must be .json or .csv")
    if config.pdf_report and Path(config.pdf_report).suffix.lower() != ".pdf":
        raise ConfigError("PDF report output must use a .pdf extension")


def validate_server_config(config: ServerConfig) -> None:
    if config.port <= 0 or config.port > 65535:
        raise ConfigError("Port must be between 1 and 65535")


def write_metrics(stats: LatencyStats, path: str) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = stats.to_dict()
    try:
        if destination.suffix.lower() == ".csv":
            with destination.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=data.keys())
                writer.writeheader()
                writer.writerow(data)
        else:
            with destination.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
                handle.write("\n")
    except OSError as exc:
        raise MetricsError(f"Unable to write metrics to '{destination}': {exc}") from exc
    logger.info("Metrics written to %s", destination)


def ensure_pdf_reporting_available() -> None:
    if not PDF_REPORTS_AVAILABLE:
        raise MetricsError("PDF reporting requires reportlab. Install with: pip install reportlab")


def _pdf_metric_rows(stats: LatencyStats) -> list[list[str]]:
    return [
        ["Packets Sent", str(stats.count_sent)],
        ["Packets Received", str(stats.count_received)],
        ["Packet Loss", str(stats.count_lost)],
        ["Success Rate", f"{stats.success_rate:.3f}%"],
        ["Mean Latency", f"{stats.mean_us:.3f} us"],
        ["P95 Latency", f"{stats.p95_us:.3f} us"],
        ["P99 Latency", f"{stats.p99_us:.3f} us"],
        ["P99.9 Latency", f"{stats.p999_us:.3f} us"],
        ["CO P99", f"{stats.co_p99_us:.3f} us"],
        ["Jitter", f"{stats.jitter_us:.3f} us"],
        ["Throughput", f"{stats.pps:.3f} pps"],
        ["Duration", f"{stats.duration_s:.3f} s"],
        ["Loop Engine", stats.loop_engine],
    ]


def write_pdf_report(stats: LatencyStats, config: TestConfig, path: str, sla_failures: Optional[list[str]] = None) -> None:
    ensure_pdf_reporting_available()
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "BlitzTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            textColor=colors.HexColor("#123243"),
            spaceAfter=10,
        )
        subtitle_style = ParagraphStyle(
            "BlitzSubtitle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#556371"),
            leading=14,
            spaceAfter=8,
        )
        section_style = ParagraphStyle(
            "BlitzSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=8,
            spaceBefore=10,
        )
        body_style = ParagraphStyle(
            "BlitzBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1c2b36"),
        )

        story: list[Any] = []
        doc = SimpleDocTemplate(
            str(destination),
            pagesize=letter,
            leftMargin=0.7 * inch,
            rightMargin=0.7 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.7 * inch,
            title=f"Neural Blitz Report - {stats.label}",
        )

        story.append(Paragraph("Neural Blitz Pro Performance Report", title_style))
        story.append(
            Paragraph(
                f"Label: <b>{stats.label}</b><br/>Target: <b>{config.host}:{config.port}</b><br/>Generated: <b>{time.strftime('%Y-%m-%d %H:%M:%S')}</b>",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 0.12 * inch))

        summary_table = PdfTable(
            [["Profile", stats.label], ["Host", config.host], ["Port", str(config.port)], ["Packet Size", f"{config.size} bytes"], ["Concurrency", str(config.concurrency)], ["Rate Limit", f"{config.rate:.0f}/s" if config.rate > 0 else "Unlimited"]],
            colWidths=[1.7 * inch, 4.3 * inch],
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f4f2")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#173343")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d7de")),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fbfc")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("Measured Results", section_style))
        results_table = PdfTable(_pdf_metric_rows(stats), colWidths=[2.2 * inch, 3.8 * inch])
        results_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6faf9")]),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdd4d0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(results_table)
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("Interpretation", section_style))
        interpretation = (
            f"This run sent <b>{stats.count_sent}</b> packets and received <b>{stats.count_received}</b>, "
            f"producing a success rate of <b>{stats.success_rate:.3f}%</b>. Tail latency reached "
            f"<b>{stats.p99_us:.3f} us</b> at P99 and <b>{stats.p999_us:.3f} us</b> at P99.9, while "
            f"measured jitter was <b>{stats.jitter_us:.3f} us</b>. Use this report to compare baseline "
            f"and candidate environments or to document network quality over time."
        )
        story.append(Paragraph(interpretation, body_style))

        if sla_failures is not None:
            story.append(Paragraph("SLA Review", section_style))
            if sla_failures:
                sla_text = "<br/>".join(f"- {failure}" for failure in sla_failures)
                story.append(Paragraph(f"<b>Status:</b> FAILED<br/>{sla_text}", body_style))
            else:
                story.append(Paragraph("<b>Status:</b> PASSED<br/>All configured SLA thresholds were met.", body_style))

        doc.build(story)
    except OSError as exc:
        raise MetricsError(f"Unable to write PDF report '{destination}': {exc}") from exc
    logger.info("PDF report written to %s", destination)


def load_metrics(path: str) -> LatencyStats:
    source = Path(path).expanduser()
    if not source.exists():
        raise MetricsError(f"Metrics file not found: {source}")
    try:
        if source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if not rows:
                raise MetricsError(f"Metrics CSV is empty: {source}")
            raw = rows[0]
        else:
            with source.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
    except OSError as exc:
        raise MetricsError(f"Unable to read metrics file '{source}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetricsError(f"Invalid JSON metrics file '{source}': {exc}") from exc
    if not isinstance(raw, dict):
        raise MetricsError(f"Metrics file '{source}' must contain a mapping")
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if value in ("", None):
            continue
        if key in {"loop_engine", "label"}:
            normalized[key] = value
            continue
        try:
            if isinstance(value, str) and value.isdigit():
                normalized[key] = int(value)
            else:
                normalized[key] = float(value) if isinstance(value, str) and any(ch in value for ch in ".eE") else value
        except ValueError:
            normalized[key] = value
    return LatencyStats.from_mapping(normalized)


def load_sla(path: str) -> SLAConfig:
    raw = load_config(path)
    section = raw.get("sla", raw)
    if not isinstance(section, dict):
        raise ConfigError("SLA config must be a mapping")
    allowed = {field.name for field in SLAConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {key: section[key] for key in section if key in allowed}
    return SLAConfig(**filtered)


def evaluate_sla(stats: LatencyStats, sla: SLAConfig) -> list[str]:
    failures: list[str] = []
    checks = [
        ("success_rate", "min", sla.min_success_rate, stats.success_rate, lambda actual, limit: actual >= limit, "%"),
        ("mean_us", "max", sla.max_mean_us, stats.mean_us, lambda actual, limit: actual <= limit, "us"),
        ("p95_us", "max", sla.max_p95_us, stats.p95_us, lambda actual, limit: actual <= limit, "us"),
        ("p99_us", "max", sla.max_p99_us, stats.p99_us, lambda actual, limit: actual <= limit, "us"),
        ("p999_us", "max", sla.max_p999_us, stats.p999_us, lambda actual, limit: actual <= limit, "us"),
        ("co_p99_us", "max", sla.max_co_p99_us, stats.co_p99_us, lambda actual, limit: actual <= limit, "us"),
        ("jitter_us", "max", sla.max_jitter_us, stats.jitter_us, lambda actual, limit: actual <= limit, "us"),
        ("pps", "min", sla.min_pps, stats.pps, lambda actual, limit: actual >= limit, "pps"),
    ]
    for metric, bound, limit, actual, comparator, unit in checks:
        if limit is None:
            continue
        if not comparator(actual, limit):
            failures.append(f"{metric} {actual:.3f}{unit} violates {bound}={limit:.3f}{unit}")
    return failures


def compare_stats(baseline: LatencyStats, candidate: LatencyStats) -> list[dict[str, Any]]:
    metrics = ["success_rate", "mean_us", "p95_us", "p99_us", "p999_us", "co_p99_us", "jitter_us", "pps"]
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        base_value = getattr(baseline, metric, 0.0)
        candidate_value = getattr(candidate, metric, 0.0)
        delta = candidate_value - base_value
        pct = (delta / base_value * 100.0) if base_value not in (0, 0.0) else None
        rows.append(
            {
                "metric": metric,
                "baseline": base_value,
                "candidate": candidate_value,
                "delta": delta,
                "delta_pct": pct,
            }
        )
    return rows


def render_stats(stats: LatencyStats) -> None:
    if USE_RICH_OUTPUT and RICH_AVAILABLE and console is not None:
        table = Table(title=f"Neural Blitz Results: {stats.label}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for metric in (
            "success_rate",
            "count_received",
            "count_lost",
            "mean_us",
            "p95_us",
            "p99_us",
            "p999_us",
            "co_p99_us",
            "jitter_us",
            "pps",
            "duration_s",
            "loop_engine",
        ):
            value = getattr(stats, metric)
            rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
            table.add_row(metric, rendered)
        console.print(table)
        return
    print(json.dumps(stats.to_dict(), indent=2))


def render_comparison(baseline: LatencyStats, candidate: LatencyStats, rows: list[dict[str, Any]]) -> None:
    if USE_RICH_OUTPUT and RICH_AVAILABLE and console is not None:
        table = Table(title=f"Comparison: {baseline.label} -> {candidate.label}")
        table.add_column("Metric")
        table.add_column("Baseline", justify="right")
        table.add_column("Candidate", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Delta %", justify="right")
        for row in rows:
            delta_pct = "n/a" if row["delta_pct"] is None else f"{row['delta_pct']:.2f}%"
            table.add_row(
                row["metric"],
                f"{row['baseline']:.3f}",
                f"{row['candidate']:.3f}",
                f"{row['delta']:+.3f}",
                delta_pct,
            )
        console.print(table)
        return
    print(json.dumps({"baseline": baseline.to_dict(), "candidate": candidate.to_dict(), "comparison": rows}, indent=2))


def render_sla_result(failures: list[str], sla_path: str) -> None:
    if not failures:
        if USE_RICH_OUTPUT and RICH_AVAILABLE and console is not None:
            console.print(Panel.fit(f"SLA PASS: {sla_path}", style="green"))
        else:
            print(f"SLA PASS: {sla_path}")
        return
    message = "\n".join(f"- {failure}" for failure in failures)
    if USE_RICH_OUTPUT and RICH_AVAILABLE and error_console is not None:
        error_console.print(Panel.fit(f"SLA FAIL: {sla_path}\n{message}", style="red"))
    else:
        print(f"SLA FAIL: {sla_path}\n{message}", file=sys.stderr)


def emit_error(message: str) -> None:
    if USE_RICH_OUTPUT and RICH_AVAILABLE and error_console is not None:
        error_console.print(Panel.fit(message, title="Error", style="bold red"))
    else:
        print(f"Error: {message}", file=sys.stderr)


def configure_logging(level: str, use_rich: bool) -> None:
    resolved = getattr(logging, level.upper(), None)
    if not isinstance(resolved, int):
        raise ConfigError(f"Invalid log level: {level}")
    handlers: list[logging.Handler]
    if use_rich and RICH_AVAILABLE and error_console is not None and RichHandler is not None:
        handlers = [RichHandler(console=error_console, markup=False, rich_tracebacks=True, show_path=False)]
    else:
        handlers = [logging.StreamHandler(sys.stderr)]
    logging.basicConfig(
        level=resolved,
        format="%(message)s" if use_rich and RICH_AVAILABLE else "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Production-ready UDP latency tester with SLA and comparison support.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--no-rich", action="store_true", help="Disable rich output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    test = subparsers.add_parser("test", help="Run a UDP latency test")
    test.add_argument("--host", default=None)
    test.add_argument("--port", "-p", type=int, default=None)
    test.add_argument("--count", "-c", type=int, default=None)
    test.add_argument("--size", "-s", type=int, default=None)
    test.add_argument("--concurrency", type=int, default=None)
    test.add_argument("--timeout", "-t", type=float, default=None)
    test.add_argument("--rate", type=float, default=None, help="Max packets/sec; 0=unlimited")
    test.add_argument("--max-retries", type=int, default=None)
    test.add_argument("--warmup", type=int, default=None, help="Warmup packets (discarded); 0=skip")
    test.add_argument("--no-co", action="store_true", help="Disable coordinated omission correction")
    test.add_argument("--progress-interval", type=float, default=None, help="Reserved for compatibility")
    test.add_argument("--no-progress", action="store_true", help="Disable progress display")
    test.add_argument("--socket-rcvbuf", type=int, default=None)
    test.add_argument("--socket-sndbuf", type=int, default=None)
    test.add_argument("--metrics-output", default=None, help="Path for JSON or CSV metrics output")
    test.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    test.add_argument("--label", default=None, help="Label to include in metrics output")
    test.add_argument("--sla", default=None, help="Path to SLA YAML config")
    test.add_argument("--fail-on-sla", action="store_true", help="Exit non-zero if SLA is violated")
    test.add_argument("--pdf-report", default=None, help="Path to write a PDF report after the test")

    server = subparsers.add_parser("server", help="Run a UDP echo server")
    server.add_argument("--bind", default=None)
    server.add_argument("--port", "-p", type=int, default=None)
    server.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    compare = subparsers.add_parser("compare", help="Compare two metrics files")
    compare.add_argument("--baseline", required=True, help="Baseline JSON or CSV metrics file")
    compare.add_argument("--candidate", required=True, help="Candidate JSON or CSV metrics file")
    compare.add_argument("--output", default=None, help="Optional path to write comparison JSON")
    compare.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    batch = subparsers.add_parser("batch", help="Run a batch of UDP latency tests from a YAML targets file")
    batch.add_argument("--targets-file", required=True, help="Path to YAML file containing a 'targets' list")
    batch.add_argument("--output", default=None, help="Optional path to write batch JSON output")
    batch.add_argument("--pdf-dir", default=None, help="Optional directory for per-target PDF reports")
    batch.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    init_config = subparsers.add_parser("init-config", help="Write a sample YAML config file")
    init_config.add_argument("--output", default=DEFAULT_CONFIG_BASENAME, help="Destination config path")

    monitor = subparsers.add_parser("monitor", help="Continuously test targets and expose HTTP metrics")
    monitor.add_argument("--targets-file", required=True, help="Path to YAML file containing a 'targets' list")
    monitor.add_argument("--bind", default=None, help="HTTP bind address")
    monitor.add_argument("--http-port", type=int, default=None, help="HTTP listen port")
    monitor.add_argument("--interval", type=int, default=None, help="Seconds between monitoring cycles")
    monitor.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    return parser


def build_test_config(args: argparse.Namespace, config_data: dict[str, Any]) -> TestConfig:
    defaults = default_test_values(config_data)
    co_correction = defaults["co_correction"]
    progress_enabled = defaults["progress_enabled"]
    if args.no_co:
        co_correction = False
    if args.no_progress:
        progress_enabled = False
    values = {
        "host": args.host if args.host is not None else defaults["host"],
        "port": args.port if args.port is not None else defaults["port"],
        "count": args.count if args.count is not None else defaults["count"],
        "size": args.size if args.size is not None else defaults["size"],
        "concurrency": args.concurrency if args.concurrency is not None else defaults["concurrency"],
        "timeout": args.timeout if args.timeout is not None else defaults["timeout"],
        "rate": args.rate if args.rate is not None else defaults["rate"],
        "max_retries": args.max_retries if args.max_retries is not None else defaults["max_retries"],
        "warmup": args.warmup if args.warmup is not None else defaults["warmup"],
        "metrics_output": args.metrics_output if args.metrics_output is not None else defaults["metrics_output"],
        "log_level": args.log_level if args.log_level is not None else defaults["log_level"],
        "socket_rcvbuf": args.socket_rcvbuf if args.socket_rcvbuf is not None else defaults["socket_rcvbuf"],
        "socket_sndbuf": args.socket_sndbuf if args.socket_sndbuf is not None else defaults["socket_sndbuf"],
        "co_correction": co_correction,
        "progress_interval": args.progress_interval if args.progress_interval is not None else defaults["progress_interval"],
        "progress_enabled": progress_enabled,
        "label": args.label if args.label is not None else defaults["label"],
        "sla_path": args.sla if args.sla is not None else defaults["sla_path"],
        "fail_on_sla": args.fail_on_sla or defaults["fail_on_sla"],
        "pdf_report": args.pdf_report if args.pdf_report is not None else defaults["pdf_report"],
    }
    return normalize_test_values(values)


def build_server_config(args: argparse.Namespace, config_data: dict[str, Any]) -> ServerConfig:
    defaults = {"bind": "0.0.0.0", "port": 9999, "log_level": "INFO"}
    defaults.update(get_config_section(config_data, "server"))
    return ServerConfig(
        bind=args.bind if args.bind is not None else defaults["bind"],
        port=args.port if args.port is not None else defaults["port"],
        log_level=args.log_level if args.log_level is not None else defaults["log_level"],
    )


def write_sample_config(path: str) -> None:
    ensure_yaml_available()
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    sample = {
        "defaults": {"log_level": "INFO"},
        "test": {
            "host": "127.0.0.1",
            "port": 9999,
            "count": 5000,
            "size": 64,
            "concurrency": 200,
            "timeout": 2.0,
            "rate": 5000,
            "max_retries": 1,
            "warmup": 100,
            "metrics_output": "metrics/latest.json",
            "socket_rcvbuf": 4_194_304,
            "socket_sndbuf": 4_194_304,
            "co_correction": True,
            "progress_enabled": True,
            "label": "candidate",
            "sla_path": "sla.yaml",
            "fail_on_sla": True,
            "pdf_report": "reports/latest.pdf",
        },
        "server": {"bind": "0.0.0.0", "port": 9999},
        "monitor": {"bind": "0.0.0.0", "http_port": 8888, "interval": 30},
        "sla": {
            "min_success_rate": 99.9,
            "max_p95_us": 1500.0,
            "max_p99_us": 2500.0,
            "max_jitter_us": 500.0,
            "min_pps": 1000.0,
        },
        "targets": [
            {"label": "hq", "host": "127.0.0.1", "port": 9999},
            {"label": "branch", "host": "127.0.0.1", "port": 9998},
        ],
    }
    try:
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(sample, handle, sort_keys=False)
    except OSError as exc:
        raise ConfigError(f"Unable to write sample config '{destination}': {exc}") from exc


def maybe_write_comparison(path: Optional[str], payload: dict[str, Any]) -> None:
    if not path:
        return
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise MetricsError(f"Unable to write comparison output '{destination}': {exc}") from exc


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


def build_monitor_config(args: argparse.Namespace, config_data: dict[str, Any]) -> MonitorConfig:
    defaults = {"bind": "0.0.0.0", "http_port": 8888, "interval": 30, "log_level": "INFO"}
    defaults.update(get_config_section(config_data, "monitor"))
    return MonitorConfig(
        bind=args.bind if args.bind is not None else defaults["bind"],
        http_port=args.http_port if args.http_port is not None else defaults["http_port"],
        interval=args.interval if args.interval is not None else defaults["interval"],
        log_level=args.log_level if args.log_level is not None else defaults["log_level"],
    )


def validate_monitor_config(config: MonitorConfig) -> None:
    if config.http_port <= 0 or config.http_port > 65535:
        raise ConfigError("HTTP port must be between 1 and 65535")
    if config.interval <= 0:
        raise ConfigError("Monitor interval must be greater than zero")


async def run_batch_tests(
    config_data: dict[str, Any],
    targets_data: dict[str, Any],
    metrics_output: Optional[str] = None,
    pdf_dir: Optional[str] = None,
) -> list[LatencyStats]:
    shared_overrides = targets_data.get("test", {})
    base_dir = Path(str(targets_data.get("__base_dir", Path.cwd())))
    if shared_overrides and not isinstance(shared_overrides, dict):
        raise ConfigError("Targets file key 'test' must be a mapping")
    results: list[LatencyStats] = []
    for index, target in enumerate(targets_data["targets"]):
        if not isinstance(target, dict):
            raise ConfigError("Each target entry must be a mapping")
        label = target.get("label") or target.get("name") or f"target-{index + 1}"
        overrides = dict(shared_overrides or {})
        overrides.update(target)
        overrides["label"] = label
        for path_key in ("metrics_output", "pdf_report", "sla_path"):
            path_value = overrides.get(path_key)
            if isinstance(path_value, str) and path_value and not Path(path_value).is_absolute():
                overrides[path_key] = str(base_dir / path_value)
        if pdf_dir:
            overrides["pdf_report"] = str(Path(pdf_dir).expanduser() / f"{label}.pdf")
        batch_config = build_test_config_from_overrides(config_data, overrides)
        validate_test_config(batch_config)
        logger.info("Batch target %s -> %s:%d", batch_config.label, batch_config.host, batch_config.port)
        stats = await run_test(batch_config)
        results.append(stats)
        if batch_config.metrics_output:
            write_metrics(stats, batch_config.metrics_output)
        if batch_config.pdf_report:
            sla_failures: Optional[list[str]] = None
            if batch_config.sla_path:
                sla_failures = evaluate_sla(stats, load_sla(batch_config.sla_path))
            write_pdf_report(stats, batch_config, batch_config.pdf_report, sla_failures)
    if metrics_output:
        destination = Path(metrics_output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("w", encoding="utf-8") as handle:
                json.dump([result.to_dict() for result in results], handle, indent=2)
                handle.write("\n")
        except OSError as exc:
            raise MetricsError(f"Unable to write batch output '{destination}': {exc}") from exc
    return results


def render_batch_results(results: list[LatencyStats]) -> None:
    if USE_RICH_OUTPUT and RICH_AVAILABLE and console is not None:
        table = Table(title="Batch Results")
        table.add_column("Label")
        table.add_column("Success", justify="right")
        table.add_column("P95 us", justify="right")
        table.add_column("P99 us", justify="right")
        table.add_column("Jitter us", justify="right")
        table.add_column("PPS", justify="right")
        for result in results:
            table.add_row(
                result.label,
                f"{result.success_rate:.2f}%",
                f"{result.p95_us:.2f}",
                f"{result.p99_us:.2f}",
                f"{result.jitter_us:.2f}",
                f"{result.pps:.2f}",
            )
        console.print(table)
        return
    print(json.dumps([result.to_dict() for result in results], indent=2))


async def run_monitor_loop(config_data: dict[str, Any], targets_file: str, monitor_config: MonitorConfig) -> None:
    try:
        from aiohttp import web
    except ImportError as exc:
        raise NeuralBlitzError("Monitor mode requires aiohttp. Install with: pip install aiohttp") from exc

    latest: dict[str, LatencyStats] = {}
    history: dict[str, list[dict[str, Any]]] = {}

    async def run_cycle() -> None:
        targets_data = load_targets_file(targets_file)
        targets_data.setdefault("test", {})
        if isinstance(targets_data["test"], dict):
            targets_data["test"]["progress_enabled"] = False
        results = await run_batch_tests(config_data, targets_data)
        for result in results:
            latest[result.label] = result
            history.setdefault(result.label, []).append(result.to_dict())
        logger.info("Monitor cycle complete: %d target(s)", len(results))

    async def metrics_json(_: web.Request) -> web.Response:
        return web.json_response({label: stats.to_dict() for label, stats in latest.items()})

    async def metrics_prometheus(_: web.Request) -> web.Response:
        lines: list[str] = []
        for label, stats in latest.items():
            lines.extend(
                [
                    f'nblitz_success_rate{{target="{label}"}} {stats.success_rate}',
                    f'nblitz_p95_us{{target="{label}"}} {stats.p95_us}',
                    f'nblitz_p99_us{{target="{label}"}} {stats.p99_us}',
                    f'nblitz_jitter_us{{target="{label}"}} {stats.jitter_us}',
                    f'nblitz_pps{{target="{label}"}} {stats.pps}',
                ]
            )
        return web.Response(text="\n".join(lines), content_type="text/plain")

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "version": __version__, "targets": len(latest)})

    async def api_targets(_: web.Request) -> web.Response:
        return web.json_response(sorted(latest.keys()))

    async def api_target(request: web.Request) -> web.Response:
        label = request.match_info["label"]
        return web.json_response(history.get(label, []))

    app = web.Application()
    app.router.add_get("/metrics", metrics_json)
    app.router.add_get("/metrics/prometheus", metrics_prometheus)
    app.router.add_get("/health", health)
    app.router.add_get("/api/targets", api_targets)
    app.router.add_get("/api/target/{label}", api_target)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, monitor_config.bind, monitor_config.http_port)
    await site.start()
    logger.info("Monitor HTTP listening on %s:%d", monitor_config.bind, monitor_config.http_port)

    try:
        while True:
            try:
                await run_cycle()
            except Exception as exc:
                logger.error("Monitor cycle failed: %s", exc)
            await asyncio.sleep(monitor_config.interval)
    finally:
        await runner.cleanup()


def execute_test(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_test_config(args, config_data)
    validate_test_config(config)
    configure_logging(config.log_level, use_rich)
    install_event_loop_policy()
    stats = asyncio.run(run_test(config))
    render_stats(stats)
    if config.metrics_output:
        write_metrics(stats, config.metrics_output)
    sla_failures: Optional[list[str]] = None
    if config.sla_path:
        sla = load_sla(config.sla_path)
        sla_failures = evaluate_sla(stats, sla)
        render_sla_result(sla_failures, config.sla_path)
    if config.pdf_report:
        write_pdf_report(stats, config, config.pdf_report, sla_failures)
    if sla_failures and config.fail_on_sla:
        return EXIT_SLA_FAILURE
    return EXIT_SUCCESS if stats.success_rate > 0 else EXIT_RUNTIME_ERROR


def execute_server(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_server_config(args, config_data)
    validate_server_config(config)
    configure_logging(config.log_level, use_rich)
    engine = install_event_loop_policy()
    logger.info("Loop engine: %s", engine)
    try:
        asyncio.run(run_server(config.bind, config.port))
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    return EXIT_SUCCESS


def execute_compare(args: argparse.Namespace, use_rich: bool) -> int:
    configure_logging(args.log_level, use_rich)
    baseline = load_metrics(args.baseline)
    candidate = load_metrics(args.candidate)
    if not baseline.label:
        baseline.label = "baseline"
    if not candidate.label:
        candidate.label = "candidate"
    rows = compare_stats(baseline, candidate)
    render_comparison(baseline, candidate, rows)
    maybe_write_comparison(
        args.output,
        {"baseline": baseline.to_dict(), "candidate": candidate.to_dict(), "comparison": rows},
    )
    return EXIT_SUCCESS


def execute_batch(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    configure_logging(args.log_level, use_rich)
    install_event_loop_policy()
    results = asyncio.run(run_batch_tests(config_data, load_targets_file(args.targets_file), args.output, args.pdf_dir))
    render_batch_results(results)
    return EXIT_SUCCESS if results else EXIT_RUNTIME_ERROR


def execute_monitor(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_monitor_config(args, config_data)
    validate_monitor_config(config)
    configure_logging(config.log_level, use_rich)
    install_event_loop_policy()
    try:
        asyncio.run(run_monitor_loop(config_data, args.targets_file, config))
    except KeyboardInterrupt:
        logger.info("Monitor interrupted")
    return EXIT_SUCCESS


def execute_init_config(args: argparse.Namespace) -> int:
    write_sample_config(args.output)
    if USE_RICH_OUTPUT and RICH_AVAILABLE and console is not None:
        console.print(Panel.fit(f"Sample config written to {Path(args.output).expanduser()}", style="green"))
    else:
        print(f"Sample config written to {Path(args.output).expanduser()}")
    return EXIT_SUCCESS


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config_data = load_config(args.config)
        use_rich = not getattr(args, "no_rich", False)
        global USE_RICH_OUTPUT
        USE_RICH_OUTPUT = use_rich and RICH_AVAILABLE
        if args.command == "test":
            return execute_test(args, config_data, use_rich)
        if args.command == "server":
            return execute_server(args, config_data, use_rich)
        if args.command == "compare":
            return execute_compare(args, use_rich)
        if args.command == "batch":
            return execute_batch(args, config_data, use_rich)
        if args.command == "init-config":
            return execute_init_config(args)
        if args.command == "monitor":
            return execute_monitor(args, config_data, use_rich)
        raise ConfigError(f"Unsupported command: {args.command}")
    except SLAFailure as exc:
        emit_error(str(exc))
        return EXIT_SLA_FAILURE
    except ConfigError as exc:
        emit_error(str(exc))
        return EXIT_CONFIG_ERROR
    except (MetricsError, NeuralBlitzError) as exc:
        emit_error(str(exc))
        return EXIT_RUNTIME_ERROR if not isinstance(exc, MetricsError) else EXIT_COMPARISON_FAILURE
    except KeyboardInterrupt:
        emit_error("Interrupted")
        return EXIT_RUNTIME_ERROR
    except Exception as exc:  # pragma: no cover - hard fail path
        logger.exception("Unexpected error")
        emit_error(f"Unexpected error: {exc}")
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
