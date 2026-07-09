"""Safety module edge-case tests."""

import pytest

from neural_blitz.errors import SafetyViolation
from neural_blitz.safety import SafetyLimits, validate_test_safety


@pytest.mark.unit
def test_timeout_bounds():
    with pytest.raises(SafetyViolation, match="timeout"):
        validate_test_safety(
            host="127.0.0.1",
            count=10,
            size=64,
            concurrency=1,
            timeout=0.001,
            rate=0,
            authorized_target=False,
            limits=SafetyLimits(),
        )


@pytest.mark.unit
def test_rate_limit():
    with pytest.raises(SafetyViolation, match="rate"):
        validate_test_safety(
            host="127.0.0.1",
            count=10,
            size=64,
            concurrency=1,
            timeout=1.0,
            rate=200_000,
            authorized_target=False,
            limits=SafetyLimits(),
        )


@pytest.mark.unit
def test_env_override_warns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEURAL_BLITZ_MAX_COUNT", "2000000")
    limits = SafetyLimits.from_env()
    assert limits.max_count == 2_000_000
