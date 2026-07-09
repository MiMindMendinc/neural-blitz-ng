"""Shared test fixtures."""

from __future__ import annotations

import asyncio

import pytest

from neural_blitz.config import TestConfig
from neural_blitz.udp_server import EchoServerProtocol


@pytest.fixture
def sample_test_config() -> TestConfig:
    return TestConfig(
        host="127.0.0.1",
        port=9999,
        count=50,
        size=64,
        concurrency=10,
        timeout=2.0,
        rate=0.0,
        warmup=0,
        progress_enabled=False,
    )


@pytest.fixture
async def echo_server():
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(EchoServerProtocol, local_addr=("127.0.0.1", 0))
    port = transport.get_extra_info("sockname")[1]
    yield port
    transport.close()
