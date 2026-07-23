"""UDP client edge-case tests."""

import asyncio
import socket
from unittest import mock

import pytest

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
async def test_send_one_retries_after_timeout():
    protocol = BlitzClientProtocol()
    transport = mock.Mock()
    protocol.transport = transport

    seq, rtt, retries, _ = await send_one(
        protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 1, TokenBucketLimiter(0)
    )

    assert (seq, rtt, retries) == (1, None, 1)
    assert transport.sendto.call_count == 2
    assert protocol._inflight == {}


@pytest.mark.unit
async def test_send_one_returns_without_transport():
    protocol = BlitzClientProtocol()

    seq, rtt, retries, scheduled = await send_one(
        protocol, ("127.0.0.1", 9000), 1, 64, 0.001, 1, TokenBucketLimiter(0)
    )

    assert (seq, rtt, retries) == (1, None, 0)
    assert scheduled > 0
    assert protocol._inflight == {}


@pytest.mark.unit
async def test_run_test_wraps_client_endpoint_error(sample_test_config):
    loop = asyncio.get_running_loop()
    with (
        mock.patch.object(loop, "create_datagram_endpoint", side_effect=OSError("permission denied")),
        pytest.raises(NeuralBlitzError, match="Unable to create UDP client endpoint: permission denied"),
    ):
        await run_test(sample_test_config, use_rich=False)


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
