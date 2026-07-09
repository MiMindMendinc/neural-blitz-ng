"""Tests for safety limits."""

import pytest

from neural_blitz.errors import SafetyViolation
from neural_blitz.safety import SafetyLimits, is_private_or_loopback, validate_test_safety


@pytest.mark.unit
def test_localhost_is_safe():
    assert is_private_or_loopback("127.0.0.1")
    assert is_private_or_loopback("localhost")


@pytest.mark.unit
def test_public_host_blocked_without_authorization():
    with pytest.raises(SafetyViolation, match="authorized"):
        validate_test_safety(
            host="8.8.8.8",
            count=100,
            size=64,
            concurrency=10,
            timeout=1.0,
            rate=0,
            authorized_target=False,
            limits=SafetyLimits(),
        )


@pytest.mark.unit
def test_public_host_allowed_with_flag():
    validate_test_safety(
        host="8.8.8.8",
        count=100,
        size=64,
        concurrency=10,
        timeout=1.0,
        rate=0,
        authorized_target=True,
        limits=SafetyLimits(),
    )


@pytest.mark.unit
def test_count_limit_enforced():
    with pytest.raises(SafetyViolation, match="count"):
        validate_test_safety(
            host="127.0.0.1",
            count=2_000_000,
            size=64,
            concurrency=10,
            timeout=1.0,
            rate=0,
            authorized_target=False,
            limits=SafetyLimits(max_count=1_000_000),
        )
