"""UDP latency test client."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
import time
from typing import Any

from neural_blitz.config import TestConfig
from neural_blitz.errors import NeuralBlitzError
from neural_blitz.latency import LatencyRecorder, build_packet, parse_packet
from neural_blitz.metrics import LatencyStats, compute_stats
from neural_blitz.safety import log_responsible_use_notice, validate_test_safety

logger = logging.getLogger("neural_blitz")

_UVLOOP_AVAILABLE = False
try:
    import uvloop

    _UVLOOP_AVAILABLE = True
except ImportError:
    pass


def install_event_loop_policy() -> str:
    if _UVLOOP_AVAILABLE and os.environ.get("NEURAL_BLITZ_NO_UVLOOP") != "1":
        uvloop.install()
        return "uvloop"
    return "asyncio"


def resolve_host(host: str, port: int) -> tuple[str, int]:
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as exc:
        raise NeuralBlitzError(f"Unable to resolve host '{host}': {exc}") from exc
    return host, port


class BlitzClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, rcvbuf: int = 4_194_304, sndbuf: int = 4_194_304) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self._inflight: dict[int, asyncio.Future[tuple[float, int]]] = {}
        self._completed: set[int] = set()
        self.count_duplicate = 0
        self.count_malformed = 0
        self.count_out_of_order = 0
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
            _version, seq_id, send_ns, _sched_ns = parse_packet(data)
        except ValueError as exc:
            self.count_malformed += 1
            logger.debug("Malformed packet from %s: %s", addr, exc)
            return
        if seq_id in self._completed:
            self.count_duplicate += 1
            return
        future = self._inflight.get(seq_id)
        if future is None or future.done():
            self.count_out_of_order += 1
            return
        rtt_us = (recv_ns - send_ns) / 1_000.0
        self._completed.add(seq_id)
        future.set_result((rtt_us, recv_ns))

    def error_received(self, exc: Exception) -> None:
        logger.error("Client socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
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
        self._max_tokens = max(1.0, rate * 0.1) if rate > 0 else 1.0
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
    def __init__(self, total: int, enabled: bool, use_rich: bool) -> None:
        self._total = total
        self._enabled = enabled
        self._done = 0
        self._received = 0
        self._start = time.monotonic()
        self._progress = None
        self._task_id: Any = None
        if enabled and use_rich:
            from rich.progress import (
                BarColumn,
                Progress,
                SpinnerColumn,
                TaskProgressColumn,
                TextColumn,
                TimeElapsedColumn,
            )

            from neural_blitz.logging_setup import error_console

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

    def __enter__(self) -> ProgressReporter:
        if self._progress is not None:
            self._progress.start()
            self._task_id = self._progress.add_task("UDP latency test", total=self._total, recv=0, expected=self._total)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
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


async def send_one(
    protocol: BlitzClientProtocol,
    addr: tuple[str, int],
    seq_id: int,
    size: int,
    timeout: float,
    max_retries: int,
    limiter: TokenBucketLimiter,
) -> tuple[int, float | None, int, int]:
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
            raise
        finally:
            protocol.unregister(seq_id)
    return seq_id, None, retries, 0


async def run_test(config: TestConfig, *, use_rich: bool = True) -> LatencyStats:
    validate_test_safety(
        host=config.host,
        count=config.count,
        size=config.size,
        concurrency=config.concurrency,
        timeout=config.timeout,
        rate=config.rate,
        authorized_target=config.authorized_target,
    )
    log_responsible_use_notice()

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
        "Starting test label=%s count=%d size=%d host=%s port=%d concurrency=%d timeout=%.2fs rate=%s",
        config.label,
        config.count,
        config.size,
        config.host,
        config.port,
        config.concurrency,
        config.timeout,
        f"{config.rate:.0f}/s" if config.rate > 0 else "unlimited",
    )

    try:
        if config.warmup > 0:
            logger.info("Warmup phase: %d packets", config.warmup)
            warmup_sem = asyncio.Semaphore(min(config.concurrency, config.warmup))
            warmup_limiter = TokenBucketLimiter(config.rate)

            async def warmup_send(seq: int) -> None:
                async with warmup_sem:
                    await send_one(protocol, addr, seq, config.size, config.timeout, 0, warmup_limiter)

            await asyncio.gather(*(warmup_send(index) for index in range(config.count, config.count + config.warmup)))

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
        with ProgressReporter(config.count, config.progress_enabled, use_rich) as progress:
            await asyncio.gather(*(bounded(index, progress) for index in range(config.count)))
        duration = time.monotonic() - t0
    finally:
        transport.close()

    stats = compute_stats(
        recorder,
        raw_rtts,
        count_sent=config.count,
        count_retried=total_retries,
        count_duplicate=protocol.count_duplicate,
        count_malformed=protocol.count_malformed,
        count_out_of_order=protocol.count_out_of_order,
        duration_s=duration,
        loop_engine=loop_engine,
        label=config.label,
        host=config.host,
        port=config.port,
    )
    logger.info(
        "Done: %d/%d (%.1f%%) in %.2fs | p50=%.1f p95=%.1f p99=%.1f us | pps=%.0f",
        stats.count_received,
        stats.count_sent,
        stats.success_rate,
        stats.duration_s,
        stats.p50_us,
        stats.p95_us,
        stats.p99_us,
        stats.pps,
    )
    return stats
