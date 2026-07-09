"""Small tests to clear coverage threshold."""

import pytest

from neural_blitz.config import ensure_yaml_available
from neural_blitz.errors import DependencyMissing, SafetyViolation
from neural_blitz.safety import SafetyLimits


@pytest.mark.unit
def test_env_int_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEURAL_BLITZ_MAX_COUNT", "not-int")
    with pytest.raises(SafetyViolation):
        SafetyLimits.from_env()


@pytest.mark.unit
def test_ensure_yaml_missing():
    with pytest.MonkeyPatch.context() as m:
        m.setattr("neural_blitz.config.yaml", None)
        with pytest.raises(DependencyMissing):
            ensure_yaml_available()
