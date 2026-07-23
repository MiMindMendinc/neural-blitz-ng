"""UDP client edge-case tests."""

import asyncio
import importlib.util
import socket
import sys
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz import udp_client
from neural_blitz.config import TestConfig
from neural_blitz.errors import NeuralBlitzError
from neural_blitz.latency import build_packet
from neural_blitz.udp_client import BlitzClientProtocol, TokenBucketLimiter, resolve_host, run_test, send_one
from neural_blitz.udp_server import EchoServerProtocol


@pytest.mark.unit
def test_resolve_host_uses_first_udp_address():
    addresses = [
        (socket.AF_INET6, socket.SOCK_DGRAM, 17, "", ("::1", 9000, 0, 0)),
        (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("127.0.0.1", 9000)),
    ]
    with mock.patch("neural_blitz.udp_client.socket.getaddrinfo", return_value=addresses):
        assert resolve_host("example.test", 9000) == ("::1", 9000)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("result", "error"),
    [
        ([], None),
        (None, socket.gaierror(socket.EAI_NONAME, "Name or service not known")),
    ],
)
def test_resolve_host_wraps_lookup_errors(result, error):
    with (
        mock.patch("neural_blitz.udp_client.socket.getaddrinfo", return_value=result, side_effect=error),
        pytest.raises(NeuralBlitzError, match="Unable to resolve host 'missing.test'"),
    ):
        resolve_host("missing.test", 9000)


@pytest.mark.unit
def test_install_event_loop_policy_uses_available_uvloop(monkeypatch):
    fake_uvloop = mock.Mock()
    module_name = "test_udp_client_with_uvloop"
    spec = importlib.util.spec_from_file_location(module_name, Path(udp_client.__file__))
    assert spec is not None and spec.loader is not None
    isolated_client = importlib.util.module_from_spec(spec)

    monkeypatch.setitem(sys.modules, "uvloop", fake_uvloop)
    sys.modules[module_name] = isolated_client
    try:
        spec.loader.exec_module(isolated_client)
        assert isolated_client.install_event_loop_policy() == "uvloop"
    finally:
        sys.modules.pop(module_name, None)

    fake_uvloop.install.assert_called_once_with()


@pytest.mark.unit
async def test_token_bucket_unlimited():
    limiter = TokenBucketLimiter(0)
    scheduled = await limiter.acquire()
    assert scheduled > 0


@pytest.mark.unit
async def test_client_protocol_tracks_malformed_duplicate_and_out_of_order_packets():
    protocol = BlitzClientProtocol()
    loop = asyncio.get_running_loop()
    response = loop.create_future()
    protocol.register(7, response)

    protocol.datagram_received(build_packet(7, 64), ("127.0.0.1", 9000))
    protocol.datagram_received(build_packet(7, 64), ("127.0.0.1", 9000))
    protocol.datagram_received(build_packet(8, 64), ("127.0.0.1", 9000))
    protocol.datagram_received(b"not a packet", ("127.0.0.1", 9000))

    assert response.done()
    assert response.result()[0] >= 0
    assert protocol.count_duplicate == 1
    assert protocol.count_out_of_order == 1
    assert protocol.count_malformed == 1


@pytest.mark.unit
async def test_client_protocol_clears_oversized_completed_set():
    protocol = BlitzClientProtocol()
    protocol._completed = set(range(131_072))
    response = asyncio.get_running_loop().create_future()
    protocol.register(131_072, response)

    protocol.datagram_received(build_packet(131_072, 64), ("127.0.0.1", 9000))

    assert response.done()
    assert protocol._completed == set()


@pytest.mark.unit
def test_client_connection_made_skips_missing_socket():
    protocol = BlitzClientProtocol()
    transport = mock.Mock()
    transport.get_extra_info.side_effect = lambda name: None if name == "socket" else ("127.0.0.1", 9000)

    protocol.connection_made(transport)

    assert protocol.transport is transport
    transport.get_extra_info.assert_called_with("socket")


@pytest.mark.unit
def test_client_connection_made_logs_buffer_tuning_error(caplog):
    protocol = BlitzClientProtocol()
    sock = mock.Mock()
    sock.setsockopt.side_effect = OSError("not permitted")
    transport = mock.Mock()
    transport.get_extra_info.return_value = sock

    with caplog.at_level("DEBUG", logger="neural_blitz"):
        protocol.connection_made(transport)

    assert "Socket buffer tuning failed: not permitted" in caplog.text
    sock.setsockopt.assert_called_once()


@pytest.mark.unit
def test_client_logs_socket_error(caplog):
    protocol = BlitzClientProtocol()

    with caplog.at_level("ERROR", logger="neural_blitz"):
        protocol.error_received(OSError("socket failed"))

    assert "Client socket error: socket failed" in caplog.text


@pytest.mark.unit
async def test_client_connection_loss_cancels_inflight_requests(caplog):
    protocol = BlitzClientProtocol()
    pending = asyncio.get_running_loop().create_future()
    protocol.register(7, pending)

    with caplog.at_level("ERROR", logger="neural_blitz"):
        protocol.connection_lost(ConnectionError("network down"))

    assert pending.cancelled()
    assert protocol._inflight == {}
    assert "Client connection lost: network down" in caplog.text


@pytest.mark.unit
async def test_client_connection_loss_keeps_completed_future_result():
    protocol = BlitzClientProtocol()
    completed = asyncio.get_running_loop().create_future()
    completed.set_result((1.0, 1))
    protocol.register(7, completed)

    protocol.connection_lost(None)

    assert completed.result() == (1.0, 1)
    assert protocol._inflight == {}


@pytest.mark.unit
async def test_send_one_retries_after_timeout():
    protocol = BlitzClientProtocol()
    transport = mock.Mock()
    protocol.transport = transport

    seq, rtt, retries, _ = await send_one(protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 1, TokenBucketLimiter(0))

    assert (seq, rtt, retries) == (1, None, 1)
    assert transport.sendto.call_count == 2
    assert protocol._inflight == {}


@pytest.mark.unit
async def test_send_one_returns_without_transport():
    protocol = BlitzClientProtocol()

    seq, rtt, retries, scheduled = await send_one(protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 1, TokenBucketLimiter(0))

    assert (seq, rtt, retries) == (1, None, 0)
    assert scheduled > 0
    assert protocol._inflight == {}


@pytest.mark.unit
async def test_send_one_does_not_cancel_future_already_completed_during_timeout():
    class CompletedProtocol(BlitzClientProtocol):
        def register(self, seq_id, future):
            super().register(seq_id, future)
            future.set_result((1.0, 1))

    protocol = CompletedProtocol()
    protocol.transport = mock.Mock()
    with mock.patch("neural_blitz.udp_client.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        seq, rtt, retries, _ = await send_one(protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 0, TokenBucketLimiter(0))

    assert (seq, rtt, retries) == (1, None, 0)


@pytest.mark.unit
async def test_send_one_unregisters_request_when_cancelled():
    protocol = BlitzClientProtocol()
    protocol.transport = mock.Mock()

    with (
        mock.patch("neural_blitz.udp_client.asyncio.wait_for", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await send_one(protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 0, TokenBucketLimiter(0))

    assert protocol._inflight == {}


@pytest.mark.unit
async def test_send_one_returns_fallback_for_negative_retry_limit():
    seq, rtt, retries, scheduled = await send_one(
        BlitzClientProtocol(), ("127.0.0.1", 9000), 1, 64, 0.001, -1, TokenBucketLimiter(0)
    )

    assert (seq, rtt, retries, scheduled) == (1, None, 0, 0)


@pytest.mark.unit
async def test_run_test_wraps_client_endpoint_error(sample_test_config):
    loop = asyncio.get_running_loop()
    with (
        mock.patch.object(loop, "create_datagram_endpoint", side_effect=OSError("permission denied")),
        pytest.raises(NeuralBlitzError, match="Unable to create UDP client endpoint: permission denied"),
    ):
        await run_test(sample_test_config, use_rich=False)


@pytest.mark.unit
async def test_run_test_records_timeout_as_unreceived_packet():
    transport = mock.Mock()
    protocol = BlitzClientProtocol()
    config = TestConfig(count=1, concurrency=1, timeout=0.01, warmup=0, progress_enabled=False)
    loop = asyncio.get_running_loop()

    with (
        mock.patch.object(loop, "create_datagram_endpoint", return_value=(transport, protocol)),
        mock.patch("neural_blitz.udp_client.send_one", return_value=(0, None, 0, 0)),
    ):
        stats = await run_test(config, use_rich=False)

    assert stats.count_sent == 1
    assert stats.count_received == 0
    transport.close.assert_called_once_with()


@pytest.mark.integration
async def test_send_one_success():
    loop = asyncio.get_running_loop()
    server_transport, _ = await loop.create_datagram_endpoint(EchoServerProtocol, local_addr=("127.0.0.1", 0))
    port = server_transport.get_extra_info("sockname")[1]

    client_transport, protocol = await loop.create_datagram_endpoint(BlitzClientProtocol, local_addr=("127.0.0.1", 0))
    try:
        seq, rtt, retries, _ = await send_one(
            protocol,
            ("127.0.0.1", port),
            99,
            64,
            2.0,
            0,
            TokenBucketLimiter(0),
        )
        assert rtt is not None
        assert retries == 0
    finally:
        client_transport.close()
        server_transport.close()
