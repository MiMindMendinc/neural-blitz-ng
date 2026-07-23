"""Regression tests for CLI and configuration error-handling paths."""

from __future__ import annotations

import builtins
import importlib.util
import runpy
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from unittest import mock

import pytest

from neural_blitz import cli
from neural_blitz.config import (
    TestConfig,
    build_test_config_from_overrides,
    coerce_bool,
    get_config_section,
    normalize_test_values,
    read_yaml,
    validate_config_file,
    write_sample_config,
)
from neural_blitz.constants import (
    EXIT_COMPARISON_FAILURE,
    EXIT_CONFIG_ERROR,
    EXIT_DEPENDENCY_MISSING,
    EXIT_INTERRUPTED,
    EXIT_RUNTIME_ERROR,
    EXIT_SAFETY_VIOLATION,
    EXIT_SLA_FAILURE,
)
from neural_blitz.errors import ComparisonFailure, ConfigError, DependencyMissing, MetricsError, SafetyViolation
from neural_blitz.metrics import LatencyStats


@pytest.mark.unit
def test_plain_renderers_include_failure_and_stats_data(capsys: pytest.CaptureFixture[str]):
    stats = LatencyStats(label="plain", success_rate=99.5, p95_us=3.0)
    cli.render_stats(stats, use_rich=False, as_json=False)
    cli.render_batch_results([stats], use_rich=False, as_json=False)
    cli.render_comparison(
        stats,
        stats,
        [{"metric": "p95_us", "baseline": 3.0, "candidate": 3.0, "delta": 0.0, "delta_pct": None}],
        use_rich=False,
        as_json=False,
        failures=["latency regression"],
    )
    output = capsys.readouterr().out
    assert '"label": "plain"' in output
    assert '"failures": [' in output


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.error_console")
def test_render_sla_failure_uses_rich_error_console(mock_error_console: mock.Mock):
    cli.render_sla_result(["p95 exceeded"], "sla.yaml", use_rich=True)
    mock_error_console.print.assert_called_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.console")
def test_rich_renderers_cover_passing_sla_and_comparison_without_failures(mock_console: mock.Mock):
    stats = LatencyStats(label="rich", p95_us=2.0)
    cli.render_sla_result([], "sla.yaml", use_rich=True)
    cli.render_comparison(
        stats,
        stats,
        [{"metric": "p95_us", "baseline": 2.0, "candidate": 2.0, "delta": 0.0, "delta_pct": 0.0}],
        use_rich=True,
        as_json=False,
    )
    assert mock_console.print.call_count == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), (" yes ", True), ("OFF", False)],
)
def test_coerce_bool_accepts_boolean_and_string_forms(value: object, expected: bool):
    assert coerce_bool(value) is expected


@pytest.mark.unit
def test_coerce_bool_rejects_non_boolean_non_string_values():
    with pytest.raises(ConfigError, match="Invalid boolean"):
        coerce_bool(1)


@pytest.mark.unit
def test_get_config_section_rejects_non_mapping_defaults():
    with pytest.raises(ConfigError, match="'defaults'"):
        get_config_section({"defaults": ["not", "a", "mapping"]}, "test")


@pytest.mark.unit
def test_normalize_test_values_handles_boolean_and_string_optional_flags():
    values = {
        "host": "127.0.0.1",
        "port": 9999,
        "count": 1,
        "size": 64,
        "concurrency": 1,
        "timeout": 1,
        "rate": 0,
        "max_retries": 0,
        "warmup": 0,
        "co_correction": False,
        "progress_enabled": True,
        "fail_on_sla": "on",
        "authorized_target": "0",
    }
    config = normalize_test_values(values)
    assert config == TestConfig(
        count=1,
        concurrency=1,
        timeout=1.0,
        warmup=0,
        co_correction=False,
        progress_enabled=True,
        fail_on_sla=True,
        authorized_target=False,
    )


@pytest.mark.unit
def test_validate_config_reports_each_malformed_target_shape(tmp_path: Path):
    path = tmp_path / "malformed-targets.yaml"
    path.write_text(
        "targets:\n"
        "  - bad-item\n"
        "  - port: 0\n"
        "  - host: localhost\n"
        "    port: bad\n",
        encoding="utf-8",
    )
    errors = validate_config_file(str(path))
    assert "targets[0] must be a mapping" in errors
    assert "targets[1] missing 'host'" in errors
    assert "targets[1] invalid port: 0" in errors
    assert "targets[2] invalid port: 'bad'" in errors


@pytest.mark.unit
def test_validate_config_reports_non_list_targets(tmp_path: Path):
    path = tmp_path / "targets-map.yaml"
    path.write_text("targets: {host: localhost}\n", encoding="utf-8")
    assert "'targets' must be a list" in validate_config_file(str(path))


@pytest.mark.unit
def test_validate_config_reports_invalid_test_settings(tmp_path: Path):
    path = tmp_path / "invalid-test.yaml"
    path.write_text("defaults:\n  count: 0\n", encoding="utf-8")
    assert "test config: Count must be greater than zero" in validate_config_file(str(path))


@pytest.mark.unit
def test_read_yaml_wraps_file_and_parser_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigError, match="Unable to read"):
        read_yaml(missing)

    valid = tmp_path / "valid.yaml"
    valid.write_text("key: value\n", encoding="utf-8")
    monkeypatch.setattr("neural_blitz.config.yaml.safe_load", mock.Mock(side_effect=ValueError("bad yaml")))
    with pytest.raises(ConfigError, match="Unable to parse"):
        read_yaml(valid)


@pytest.mark.unit
def test_write_sample_config_wraps_write_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    destination = tmp_path / "config.yaml"
    monkeypatch.setattr(Path, "write_text", mock.Mock(side_effect=OSError("disk full")))
    with pytest.raises(ConfigError, match="Unable to write sample config"):
        write_sample_config(str(destination))


@pytest.mark.unit
def test_config_module_handles_missing_yaml_dependency(monkeypatch: pytest.MonkeyPatch):
    source_path = Path(cli.__file__).with_name("config.py")
    module_name = "test_config_without_pyyaml"
    original_import = builtins.__import__

    def import_without_yaml(name: str, *args: object, **kwargs: object):
        if name == "yaml":
            raise ImportError("PyYAML deliberately unavailable")
        return original_import(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", import_without_yaml)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    sys.modules.pop(module_name, None)
    assert module.yaml is None


@pytest.mark.unit
def test_overrides_ignore_unknown_and_none_values():
    config = build_test_config_from_overrides({}, {"unknown": 1, "count": None})
    assert config.count == TestConfig().count


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (SafetyViolation("unsafe"), EXIT_SAFETY_VIOLATION),
        (ConfigError("bad config"), EXIT_CONFIG_ERROR),
        (DependencyMissing("missing"), EXIT_DEPENDENCY_MISSING),
        (ComparisonFailure("regression"), EXIT_COMPARISON_FAILURE),
        (MetricsError("bad metrics"), EXIT_RUNTIME_ERROR),
        (KeyboardInterrupt(), EXIT_INTERRUPTED),
        (RuntimeError("unexpected"), EXIT_RUNTIME_ERROR),
    ],
)
def test_main_maps_handler_exceptions_to_exit_codes(
    monkeypatch: pytest.MonkeyPatch, exception: Exception, expected: int
):
    monkeypatch.setattr(cli, "execute_version", mock.Mock(side_effect=exception))
    monkeypatch.setattr(cli, "emit_error", mock.Mock())
    assert cli.main(["version"]) == expected


@pytest.mark.unit
def test_main_rejects_unknown_handler(monkeypatch: pytest.MonkeyPatch):
    parser = mock.Mock()
    parser.parse_args.return_value = Namespace(command="unknown", config=None, no_rich=True)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    monkeypatch.setattr(cli, "emit_error", mock.Mock())
    assert cli.main(["unknown"]) == EXIT_CONFIG_ERROR


@pytest.mark.unit
def test_build_test_config_applies_disable_and_authorization_flags():
    args = Namespace(
        host=None,
        port=None,
        count=None,
        size=None,
        concurrency=None,
        timeout=None,
        rate=None,
        max_retries=None,
        warmup=None,
        no_co=True,
        no_progress=False,
        socket_rcvbuf=None,
        socket_sndbuf=None,
        metrics_output=None,
        log_level=None,
        label=None,
        sla=None,
        fail_on_sla=False,
        pdf_report=None,
        i_understand_authorized_target=True,
    )
    config = cli.build_test_config(args, {})
    assert config.co_correction is False
    assert config.progress_enabled is True
    assert config.authorized_target is True


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_server", new_callable=mock.AsyncMock, side_effect=KeyboardInterrupt)
def test_execute_server_returns_interrupted_for_keyboard_interrupt(mock_run_server: mock.AsyncMock):
    args = Namespace(bind="127.0.0.1", port=9999, log_level="INFO")
    assert cli.execute_server(args, {}, use_rich=False) == EXIT_INTERRUPTED
    mock_run_server.assert_awaited_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_monitor_loop", new_callable=mock.AsyncMock, side_effect=KeyboardInterrupt)
@mock.patch("neural_blitz.cli.load_targets_file", return_value={"targets": [{"host": "127.0.0.1"}]})
def test_execute_monitor_returns_interrupted_for_keyboard_interrupt(
    mock_load_targets: mock.Mock, mock_monitor: mock.AsyncMock
):
    args = Namespace(
        targets_file="targets.yaml",
        bind=None,
        http_port=None,
        interval=None,
        log_level="INFO",
        i_understand_authorized_target=False,
    )
    assert cli.execute_monitor(args, {}, use_rich=False) == EXIT_INTERRUPTED
    mock_load_targets.assert_called_once_with("targets.yaml")
    mock_monitor.assert_awaited_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.render_comparison")
@mock.patch("neural_blitz.cli.load_metrics")
def test_execute_compare_assigns_labels_to_unlabelled_metrics(mock_load_metrics: mock.Mock, mock_render: mock.Mock):
    mock_load_metrics.side_effect = [LatencyStats(label=""), LatencyStats(label="")]
    args = Namespace(
        baseline="baseline.json",
        candidate="candidate.json",
        output=None,
        json=False,
        max_p95_regression=None,
        max_p99_regression=None,
        max_loss_regression=None,
        max_success_regression=None,
        fail_on_regression=False,
        log_level="INFO",
    )
    assert cli.execute_compare(args, use_rich=False) == 0
    baseline, candidate, *_ = mock_render.call_args.args
    assert (baseline.label, candidate.label) == ("baseline", "candidate")


@pytest.mark.unit
@mock.patch("neural_blitz.cli.load_sla", side_effect=DependencyMissing("PyYAML unavailable"))
def test_execute_validate_sla_serializes_load_errors(mock_load_sla: mock.Mock, capsys: pytest.CaptureFixture[str]):
    assert cli.execute_validate_sla(Namespace(path="sla.yaml", json=True)) == EXIT_CONFIG_ERROR
    assert "PyYAML unavailable" in capsys.readouterr().out
    mock_load_sla.assert_called_once_with("sla.yaml")


@pytest.mark.unit
@mock.patch("neural_blitz.cli.RICH_AVAILABLE", True)
@mock.patch("neural_blitz.cli.console")
@mock.patch("neural_blitz.cli.write_sample_config")
def test_execute_init_config_uses_rich_success_panel(
    mock_write: mock.Mock, mock_console: mock.Mock, tmp_path: Path
):
    output = tmp_path / "nested" / "config.yaml"
    assert cli.execute_init_config(Namespace(output=str(output)), use_rich=True) == 0
    mock_write.assert_called_once_with(str(output))
    mock_console.print.assert_called_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.run_batch_tests", new_callable=mock.AsyncMock, return_value=[])
@mock.patch("neural_blitz.cli.load_targets_file", return_value={"targets": [{"host": "127.0.0.1"}]})
def test_execute_batch_authorizes_targets_before_running(
    mock_load_targets: mock.Mock, mock_run_batch: mock.AsyncMock
):
    targets = mock_load_targets.return_value
    args = Namespace(
        targets_file="targets.yaml",
        output=None,
        pdf_dir=None,
        json=True,
        log_level="INFO",
        i_understand_authorized_target=True,
    )
    assert cli.execute_batch(args, {}, use_rich=False) == EXIT_RUNTIME_ERROR
    assert targets["test"]["authorized_target"] is True
    mock_run_batch.assert_awaited_once()


@pytest.mark.unit
def test_authorization_flag_leaves_non_mapping_test_section_unchanged():
    targets = {"test": "not-a-mapping"}
    cli._apply_authorized_flag({}, targets, authorized=True)
    assert targets["test"] == "not-a-mapping"


@pytest.mark.unit
@mock.patch("neural_blitz.cli.write_pdf_report")
@mock.patch("neural_blitz.cli.write_metrics")
@mock.patch("neural_blitz.cli.render_sla_result")
@mock.patch("neural_blitz.cli.evaluate_sla", return_value=["p95 exceeded"])
@mock.patch("neural_blitz.cli.load_sla", return_value={})
@mock.patch("neural_blitz.cli.run_test", new_callable=mock.AsyncMock)
def test_execute_test_writes_outputs_and_fails_on_sla(
    mock_run_test: mock.AsyncMock,
    mock_load_sla: mock.Mock,
    mock_evaluate_sla: mock.Mock,
    mock_render_sla: mock.Mock,
    mock_write_metrics: mock.Mock,
    mock_write_pdf: mock.Mock,
):
    mock_run_test.return_value = LatencyStats(success_rate=100.0)
    args = Namespace(
        host=None,
        port=None,
        count=None,
        size=None,
        concurrency=None,
        timeout=None,
        rate=None,
        max_retries=None,
        warmup=None,
        no_co=False,
        no_progress=False,
        socket_rcvbuf=None,
        socket_sndbuf=None,
        metrics_output="metrics.json",
        json=True,
        log_level=None,
        label=None,
        sla="limits.yaml",
        fail_on_sla=True,
        pdf_report="report.pdf",
        i_understand_authorized_target=False,
    )
    assert cli.execute_test(args, {}, use_rich=False) == EXIT_SLA_FAILURE
    mock_load_sla.assert_called_once_with("limits.yaml")
    mock_evaluate_sla.assert_called_once()
    mock_render_sla.assert_called_once()
    mock_write_metrics.assert_called_once()
    mock_write_pdf.assert_called_once()


@pytest.mark.unit
@mock.patch("neural_blitz.cli.load_sla", side_effect=ConfigError("invalid SLA"))
def test_execute_validate_sla_prints_load_errors(mock_load_sla: mock.Mock, capsys: pytest.CaptureFixture[str]):
    assert cli.execute_validate_sla(Namespace(path="sla.yaml", json=False)) == EXIT_CONFIG_ERROR
    assert "ERROR: invalid SLA" in capsys.readouterr().err
    mock_load_sla.assert_called_once_with("sla.yaml")


@pytest.mark.unit
def test_module_entrypoint_runs_version_command():
    result = subprocess.run(
        [sys.executable, "-m", "neural_blitz.cli", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "neural-blitz" in result.stdout


@pytest.mark.unit
def test_cli_main_guard_exits_with_main_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "argv", ["neural-blitz", "version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(cli.__file__)), run_name="__main__")
    assert exc.value.code == 0
