"""Monitor and batch helper tests."""

import textwrap
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz.config import ConfigError, load_targets_file
from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import run_batch_tests


@pytest.mark.unit
def test_load_targets_file_rejects_empty(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("targets: []\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_targets_file(str(bad))


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test")
async def test_run_batch_tests_single_target(mock_run_test, tmp_path: Path):
    mock_run_test.return_value = LatencyStats(label="local", success_rate=100.0, host="127.0.0.1", port=9999)
    targets_file = tmp_path / "targets.yaml"
    targets_file.write_text(
        textwrap.dedent(
            """
            targets:
              - label: local
                host: 127.0.0.1
                port: 9999
            """
        ),
        encoding="utf-8",
    )
    data = load_targets_file(str(targets_file))
    out = tmp_path / "batch.json"
    results = await run_batch_tests({}, data, metrics_output=str(out))
    assert len(results) == 1
    assert out.exists()
    mock_run_test.assert_called_once()


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test", side_effect=RuntimeError("boom"))
async def test_run_batch_continues_on_target_failure(mock_run_test, tmp_path: Path):
    targets_file = tmp_path / "targets.yaml"
    targets_file.write_text(
        "targets:\n  - label: local\n    host: 127.0.0.1\n    port: 9999\n",
        encoding="utf-8",
    )
    data = load_targets_file(str(targets_file))
    results = await run_batch_tests({}, data)
    assert results == []
    mock_run_test.assert_called_once()
