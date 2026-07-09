"""Tests for SLA evaluation."""

import pytest

from neural_blitz.metrics import LatencyStats
from neural_blitz.sla import SLAConfig, evaluate_sla, validate_sla_config


@pytest.mark.unit
def test_sla_pass():
    stats = LatencyStats(success_rate=99.95, p95_us=100.0, p99_us=200.0, jitter_us=10.0, pps=5000.0, loss_rate=0.05)
    sla = SLAConfig(min_success_rate=99.9, max_p95_us=150.0, max_p99_us=250.0, max_jitter_us=50.0, min_pps=1000.0)
    assert evaluate_sla(stats, sla) == []


@pytest.mark.unit
def test_sla_fail_lists_violations():
    stats = LatencyStats(success_rate=90.0, p95_us=5000.0, loss_rate=10.0)
    sla = SLAConfig(min_success_rate=99.0, max_p95_us=100.0, max_loss_rate=1.0)
    failures = evaluate_sla(stats, sla)
    assert len(failures) >= 2
    assert any("success_rate" in f for f in failures)
    assert any("p95_us" in f for f in failures)


@pytest.mark.unit
def test_validate_sla_config_rejects_bad_success_rate():
    errors = validate_sla_config(SLAConfig(min_success_rate=150.0))
    assert errors
