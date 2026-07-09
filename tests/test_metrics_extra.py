"""Metrics edge-case tests."""

from pathlib import Path

import pytest

from neural_blitz.errors import ConfigError, MetricsError
from neural_blitz.metrics import load_metrics, validate_metrics_output_path


@pytest.mark.unit
def test_load_metrics_missing():
    with pytest.raises(MetricsError):
        load_metrics("/no/such/metrics.json")


@pytest.mark.unit
def test_validate_metrics_output_bad_suffix():
    with pytest.raises(ConfigError):
        validate_metrics_output_path("metrics/out.txt")


@pytest.mark.unit
def test_load_metrics_empty_csv(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("count_sent\n", encoding="utf-8")
    with pytest.raises(MetricsError, match="empty"):
        load_metrics(str(path))
