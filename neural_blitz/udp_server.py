"""UDP echo server for latency testing."""

from __future__ import annotations

import asyncio
import logging
import signal
import socket

from neural_blitz.errors import NeuralBlitzError

logger = logging.getLogger("neural_blitz")


class EchoServerProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
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

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.error("Echo server connection lost: %s", exc)
        logger.info("Echo server shut down after %d packets", self.packet_count)


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

    logger.info("Echo server on %s:%d — Ctrl+C to stop", bind, port)
    try:
        await stop
    except asyncio.CancelledError:
        logger.debug("Server cancelled")
    finally:
        transport.close()
