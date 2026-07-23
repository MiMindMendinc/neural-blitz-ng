"""UDP echo server for latency testing."""

from __future__ import annotations

import asyncio
import logging
import signal
import socket
import time

from neural_blitz.constants import DEFAULT_MAX_PACKET_SIZE, HEADER_SIZE
from neural_blitz.errors import NeuralBlitzError
from neural_blitz.latency import parse_packet

logger = logging.getLogger("neural_blitz")


class EchoServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, max_packet_size: int = DEFAULT_MAX_PACKET_SIZE, rate_limit: float = 0.0) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.packet_count = 0
        self.dropped_packets = 0
        self.max_packet_size = max_packet_size
        self.rate_limit = rate_limit
        self._clients: dict[str, tuple[float, float]] = {}

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
        now = time.monotonic()
        tokens, last = self._clients.get(host, (self.rate_limit, now))
        tokens = min(self.rate_limit, tokens + (now - last) * self.rate_limit)
        if tokens < 1:
            self._clients[host] = (tokens, now)
            return False
        self._clients[host] = (tokens - 1, now)
        return True

    def error_received(self, exc: Exception) -> None:
        logger.error("Echo server socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.error("Echo server connection lost: %s", exc)
        logger.info("Echo server shut down after %d packets; dropped %d invalid or rate-limited packets", self.packet_count, self.dropped_packets)


async def run_server(
    bind: str,
    port: int,
    *,
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
    rate_limit: float = 0.0,
) -> None:
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: EchoServerProtocol(max_packet_size=max_packet_size, rate_limit=rate_limit),
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
