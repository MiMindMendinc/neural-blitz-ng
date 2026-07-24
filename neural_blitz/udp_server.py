"""UDP echo server for latency testing."""

from __future__ import annotations

import asyncio
import logging
import signal
import socket
import time
from collections.abc import Callable

from neural_blitz.constants import DEFAULT_MAX_PACKET_SIZE, HEADER_SIZE
from neural_blitz.errors import NeuralBlitzError
from neural_blitz.latency import parse_packet

logger = logging.getLogger("neural_blitz")

DEFAULT_CLIENT_STATE_TTL = 300.0
DEFAULT_MAX_TRACKED_CLIENTS = 10_000
DEFAULT_CLEANUP_INTERVAL = 60.0


class EchoServerProtocol(asyncio.DatagramProtocol):
    """UDP echo protocol with bounded, idle-expiring per-source rate-limit state.

    At most ``max_tracked_clients`` token buckets are retained.  Idle buckets
    expire after ``client_state_ttl`` seconds and periodic cleanup avoids an
    unbounded per-packet scan.  When full, the least recently seen source
    (then lexicographically smallest host) is evicted deterministically.
    """

    def __init__(
        self,
        max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
        rate_limit: float = 0.0,
        *,
        max_tracked_clients: int = DEFAULT_MAX_TRACKED_CLIENTS,
        client_state_ttl: float = DEFAULT_CLIENT_STATE_TTL,
        cleanup_interval: float = DEFAULT_CLEANUP_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_tracked_clients <= 0:
            raise ValueError("max_tracked_clients must be greater than zero")
        if client_state_ttl <= 0:
            raise ValueError("client_state_ttl must be greater than zero")
        if cleanup_interval <= 0:
            raise ValueError("cleanup_interval must be greater than zero")
        self.transport: asyncio.DatagramTransport | None = None
        self.packet_count = 0
        self.dropped_packets = 0
        self.max_packet_size = max_packet_size
        self.rate_limit = rate_limit
        self.max_tracked_clients = max_tracked_clients
        self.client_state_ttl = client_state_ttl
        self.cleanup_interval = cleanup_interval
        self._clock = clock
        self._clients: dict[str, tuple[float, float]] = {}
        self._last_cleanup = clock()

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
        if len(data) < HEADER_SIZE or len(data) > self.max_packet_size:
            self.dropped_packets += 1
            return
        try:
            parse_packet(data)
        except ValueError:
            self.dropped_packets += 1
            return
        if self.rate_limit and not self._allow(addr[0]):
            self.dropped_packets += 1
            return
        if self.transport is None:
            return
        self.packet_count += 1
        self.transport.sendto(data, addr)

    def _allow(self, host: str) -> bool:
        now = self._clock()
        if now - self._last_cleanup >= self.cleanup_interval:
            self._cleanup_clients(now)

        state = self._clients.get(host)
        if state is not None and now - state[1] >= self.client_state_ttl:
            del self._clients[host]
            state = None
        if state is None:
            if len(self._clients) >= self.max_tracked_clients:
                self._evict_client()
            tokens, last = max(1.0, self.rate_limit), now
        else:
            tokens, last = state
        capacity = max(1.0, self.rate_limit)
        tokens = min(capacity, tokens + max(0.0, now - last) * self.rate_limit)
        if tokens < 1:
            self._clients[host] = (tokens, now)
            return False
        self._clients[host] = (tokens - 1, now)
        return True

    def _cleanup_clients(self, now: float) -> None:
        self._clients = {host: state for host, state in self._clients.items() if now - state[1] < self.client_state_ttl}
        self._last_cleanup = now

    def _evict_client(self) -> None:
        host = min(self._clients, key=lambda client: (self._clients[client][1], client))
        del self._clients[host]

    def error_received(self, exc: Exception) -> None:
        logger.error("Echo server socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.error("Echo server connection lost: %s", exc)
        logger.info(
            "Echo server shut down after %d packets; dropped %d invalid or rate-limited packets",
            self.packet_count,
            self.dropped_packets,
        )


async def run_server(
    bind: str,
    port: int,
    *,
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
    rate_limit: float = 0.0,
    max_tracked_clients: int = DEFAULT_MAX_TRACKED_CLIENTS,
    client_state_ttl: float = DEFAULT_CLIENT_STATE_TTL,
    cleanup_interval: float = DEFAULT_CLEANUP_INTERVAL,
) -> None:
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: EchoServerProtocol(
                max_packet_size=max_packet_size,
                rate_limit=rate_limit,
                max_tracked_clients=max_tracked_clients,
                client_state_ttl=client_state_ttl,
                cleanup_interval=cleanup_interval,
            ),
            local_addr=(bind, port),
        )
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

    logger.info("Echo server on %s:%d — Ctrl+C to stop", bind, port)
    try:
        await stop
    except asyncio.CancelledError:
        logger.debug("Server cancelled")
    finally:
        transport.close()
