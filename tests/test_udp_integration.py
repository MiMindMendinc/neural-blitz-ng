"""UDP integration tests with local echo server."""

import pytest

from neural_blitz.config import TestConfig
from neural_blitz.udp_client import run_test


@pytest.mark.integration
async def test_udp_echo_happy_path(echo_server: int):
    config = TestConfig(
        host="127.0.0.1",
        port=echo_server,
        count=20,
        size=64,
        concurrency=5,
        timeout=2.0,
        warmup=0,
        progress_enabled=False,
    )
    stats = await run_test(config, use_rich=False)
    assert stats.count_received > 0
    assert stats.success_rate > 50.0
    assert stats.p50_us > 0.0


@pytest.mark.integration
async def test_udp_echo_high_success_rate(echo_server: int):
    config = TestConfig(
        host="127.0.0.1",
        port=echo_server,
        count=50,
        concurrency=10,
        timeout=2.0,
        warmup=0,
        progress_enabled=False,
    )
    stats = await run_test(config, use_rich=False)
    assert stats.success_rate >= 80.0
