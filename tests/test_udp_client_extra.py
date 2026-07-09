"""UDP client edge-case tests."""

import asyncio

import pytest

from neural_blitz.udp_client import TokenBucketLimiter, send_one
from neural_blitz.udp_server import EchoServerProtocol


@pytest.mark.unit
async def test_token_bucket_unlimited():
    limiter = TokenBucketLimiter(0)
    scheduled = await limiter.acquire()
    assert scheduled > 0


@pytest.mark.integration
async def test_send_one_timeout():
    loop = asyncio.get_running_loop()
    from neural_blitz.udp_client import BlitzClientProtocol

    transport, protocol = await loop.create_datagram_endpoint(BlitzClientProtocol, local_addr=("127.0.0.1", 0))
    try:
        seq, rtt, retries, _ = await send_one(
            protocol,
            ("127.0.0.1", 59999),
            1,
            64,
            0.05,
            0,
            TokenBucketLimiter(0),
        )
        assert seq == 1
        assert rtt is None
        assert retries == 0
    finally:
        transport.close()


@pytest.mark.integration
async def test_send_one_success():
    loop = asyncio.get_running_loop()
    server_transport, _ = await loop.create_datagram_endpoint(EchoServerProtocol, local_addr=("127.0.0.1", 0))
    port = server_transport.get_extra_info("sockname")[1]
    from neural_blitz.udp_client import BlitzClientProtocol

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
