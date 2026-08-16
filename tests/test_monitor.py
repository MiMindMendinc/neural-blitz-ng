"""Monitor and batch helper tests."""

import textwrap
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz.config import PROFILES_DIR, ConfigError, build_test_config_from_overrides, load_targets_file
from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import TargetState, _initialize_target_states, run_batch_tests


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


@pytest.mark.unit
@pytest.mark.parametrize(
    "targets_data, error",
    [
        ({"targets": [], "test": "not-a-mapping"}, "Config section 'test' must be a mapping"),
        ({"targets": ["not-a-mapping"]}, "Each target entry must be a mapping"),
    ],
)
async def test_run_batch_tests_rejects_malformed_target_data(targets_data, error):
    with pytest.raises(ConfigError, match=error):
        await run_batch_tests({}, targets_data)


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test")
async def test_run_batch_tests_records_failures_and_writes_successful_results(mock_run_test, tmp_path: Path):
    successful = LatencyStats(label="good", success_rate=100.0, host="127.0.0.1", port=9999)
    mock_run_test.side_effect = [successful, RuntimeError("connection refused")]
    failures: dict[str, str] = {}
    output = tmp_path / "results" / "batch.json"

    results = await run_batch_tests(
        {},
        {
            "targets": [
                {"label": "good", "host": "127.0.0.1", "port": 9999},
                {"label": "bad", "host": "127.0.0.1", "port": 9998},
            ]
        },
        metrics_output=str(output),
        failures=failures,
    )

    assert results == [successful]
    assert failures == {"bad": "connection refused"}
    assert output.exists()
    assert '"label": "good"' in output.read_text(encoding="utf-8")


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test")
async def test_batch_honors_targets_file_defaults(mock_run_test, tmp_path: Path):
    mock_run_test.return_value = LatencyStats(label="uplink", success_rate=100.0, host="127.0.0.1", port=9999)
    targets_file = tmp_path / "targets.yaml"
    targets_file.write_text(
        textwrap.dedent(
            """
            defaults:
              count: 200
              concurrency: 8
              rate: 50
            targets:
              - label: uplink
                host: 127.0.0.1
                port: 9999
            """
        ),
        encoding="utf-8",
    )
    data = load_targets_file(str(targets_file))
    await run_batch_tests({}, data)
    config = mock_run_test.call_args.args[0]
    assert config.count == 200
    assert config.concurrency == 8
    assert config.rate == 50.0


@pytest.mark.integration
@mock.patch("neural_blitz.monitor.run_test")
async def test_starlink_profile_defaults_apply_to_batch(mock_run_test):
    mock_run_test.return_value = LatencyStats(label="starlink-uplink", success_rate=100.0)
    data = load_targets_file(str(PROFILES_DIR / "starlink.yaml"))
    await run_batch_tests({}, data)
    config = mock_run_test.call_args.args[0]
    assert config.count == 200
    assert config.concurrency == 8
    assert config.rate == 50.0


@pytest.mark.unit
def test_initialize_target_states_merges_defaults_into_shared_overrides():
    states: dict[str, TargetState] = {}
    with mock.patch(
        "neural_blitz.monitor.build_test_config_from_overrides",
        wraps=build_test_config_from_overrides,
    ) as build:
        _initialize_target_states(
            {},
            {
                "defaults": {"count": 200, "concurrency": 8, "rate": 50},
                "targets": [{"label": "uplink", "host": "127.0.0.1", "port": 9999}],
            },
            states,
        )
    overrides = build.call_args.args[1]
    assert overrides["count"] == 200
    assert overrides["concurrency"] == 8
    assert overrides["rate"] == 50
    assert "uplink" in states
