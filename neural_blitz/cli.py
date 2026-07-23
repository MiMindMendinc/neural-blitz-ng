"""Command-line interface for Neural Blitz NG."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

from neural_blitz.compare import ComparisonThresholds, compare_stats, evaluate_comparison, write_comparison_output
from neural_blitz.config import (
    MonitorConfig,
    ServerConfig,
    TestConfig,
    coerce_bool,
    default_test_values,
    get_config_section,
    load_config,
    load_targets_file,
    normalize_test_values,
    validate_config_file,
    validate_monitor_config,
    validate_server_config,
    validate_test_config,
    write_sample_config,
)
from neural_blitz.constants import (
    APP_NAME,
    DEFAULT_CONFIG_BASENAME,
    EXIT_COMPARISON_FAILURE,
    EXIT_CONFIG_ERROR,
    EXIT_DEPENDENCY_MISSING,
    EXIT_INTERRUPTED,
    EXIT_RUNTIME_ERROR,
    EXIT_SAFETY_VIOLATION,
    EXIT_SLA_FAILURE,
    EXIT_SUCCESS,
    __version__,
)
from neural_blitz.errors import (
    ComparisonFailure,
    ConfigError,
    DependencyMissing,
    MetricsError,
    NeuralBlitzError,
    SafetyViolation,
)
from neural_blitz.logging_setup import RICH_AVAILABLE, configure_logging, console, emit_error, error_console
from neural_blitz.metrics import LatencyStats, load_metrics, write_metrics
from neural_blitz.monitor import run_batch_tests, run_monitor_loop
from neural_blitz.report_pdf import write_pdf_report
from neural_blitz.sla import evaluate_sla, load_sla, validate_sla_config
from neural_blitz.udp_client import install_event_loop_policy, run_test
from neural_blitz.udp_server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Local-first UDP latency benchmarking and monitoring for authorized operators.",
        epilog="Neural Blitz NG is for authorized monitoring only. Default targets are localhost.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--no-rich", action="store_true", help="Disable Rich terminal output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    test = subparsers.add_parser("test", help="Run a UDP latency test against one target")
    test.add_argument("--host", default=None, help="Target host (default: 127.0.0.1)")
    test.add_argument("--port", "-p", type=int, default=None)
    test.add_argument("--count", "-c", type=int, default=None)
    test.add_argument("--size", "-s", type=int, default=None)
    test.add_argument("--concurrency", type=int, default=None)
    test.add_argument("--timeout", "-t", type=float, default=None)
    test.add_argument("--rate", type=float, default=None, help="Max packets/sec; 0=unlimited")
    test.add_argument("--max-retries", type=int, default=None)
    test.add_argument("--warmup", type=int, default=None)
    test.add_argument("--no-co", action="store_true", help="Disable coordinated omission correction")
    test.add_argument("--no-progress", action="store_true")
    test.add_argument("--socket-rcvbuf", type=int, default=None)
    test.add_argument("--socket-sndbuf", type=int, default=None)
    test.add_argument("--metrics-output", default=None)
    test.add_argument("--json", action="store_true", help="Emit machine-readable JSON stats")
    test.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    test.add_argument("--label", default=None)
    test.add_argument("--sla", default=None, help="Path to SLA YAML")
    test.add_argument("--fail-on-sla", action="store_true")
    test.add_argument("--pdf-report", default=None)
    test.add_argument(
        "--i-understand-authorized-target",
        action="store_true",
        help="Confirm you have permission to benchmark the target host",
    )

    server = subparsers.add_parser("server", help="Run a UDP echo server")
    server.add_argument("--bind", default=None)
    server.add_argument("--port", "-p", type=int, default=None)
    server.add_argument("--max-packet-size", type=int, default=None)
    server.add_argument("--rate-limit", type=float, default=None, help="Maximum packets/sec per source; 0=unlimited")
    server.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    batch = subparsers.add_parser("batch", help="Run tests for all targets in a YAML file")
    batch.add_argument("--targets-file", required=True)
    batch.add_argument("--output", default=None)
    batch.add_argument("--pdf-dir", default=None)
    batch.add_argument("--json", action="store_true")
    batch.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    batch.add_argument("--i-understand-authorized-target", action="store_true")

    monitor = subparsers.add_parser("monitor", help="Continuously test targets and expose HTTP metrics")
    monitor.add_argument("--targets-file", required=True)
    monitor.add_argument("--bind", default=None)
    monitor.add_argument("--http-port", type=int, default=None)
    monitor.add_argument("--interval", type=int, default=None)
    monitor.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    monitor.add_argument("--i-understand-authorized-target", action="store_true")

    compare = subparsers.add_parser("compare", help="Compare baseline and candidate metrics")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output", default=None)
    compare.add_argument("--json", action="store_true")
    compare.add_argument("--max-p95-regression", type=float, default=None)
    compare.add_argument("--max-p99-regression", type=float, default=None)
    compare.add_argument("--max-loss-regression", type=float, default=None)
    compare.add_argument("--max-success-regression", type=float, default=None)
    compare.add_argument("--fail-on-regression", action="store_true")
    compare.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    validate_config = subparsers.add_parser("validate-config", help="Validate a YAML configuration file")
    validate_config.add_argument("path", nargs="?", default=DEFAULT_CONFIG_BASENAME)
    validate_config.add_argument("--json", action="store_true")

    validate_sla = subparsers.add_parser("validate-sla", help="Validate an SLA YAML file")
    validate_sla.add_argument("path", nargs="?", default="sla.yaml")
    validate_sla.add_argument("--json", action="store_true")

    version_cmd = subparsers.add_parser("version", help="Print version information")
    version_cmd.add_argument("--json", action="store_true")

    init_config = subparsers.add_parser(
        "init-config", help="Write a sample YAML config (alias: validate-config template)"
    )
    init_config.add_argument("--output", default=DEFAULT_CONFIG_BASENAME)

    return parser


def build_test_config(args: argparse.Namespace, config_data: dict[str, Any]) -> TestConfig:
    defaults = default_test_values(config_data)
    co_correction = defaults["co_correction"]
    progress_enabled = defaults["progress_enabled"]
    authorized_target = defaults.get("authorized_target", False)
    if args.no_co:
        co_correction = False
    if getattr(args, "no_progress", False):
        progress_enabled = False
    if getattr(args, "i_understand_authorized_target", False):
        authorized_target = True
    values = {
        "host": args.host if args.host is not None else defaults["host"],
        "port": args.port if args.port is not None else defaults["port"],
        "count": args.count if args.count is not None else defaults["count"],
        "size": args.size if args.size is not None else defaults["size"],
        "concurrency": args.concurrency if args.concurrency is not None else defaults["concurrency"],
        "timeout": args.timeout if args.timeout is not None else defaults["timeout"],
        "rate": args.rate if args.rate is not None else defaults["rate"],
        "max_retries": args.max_retries if args.max_retries is not None else defaults["max_retries"],
        "warmup": args.warmup if args.warmup is not None else defaults["warmup"],
        "metrics_output": args.metrics_output if args.metrics_output is not None else defaults["metrics_output"],
        "log_level": args.log_level if args.log_level is not None else defaults["log_level"],
        "socket_rcvbuf": args.socket_rcvbuf if args.socket_rcvbuf is not None else defaults["socket_rcvbuf"],
        "socket_sndbuf": args.socket_sndbuf if args.socket_sndbuf is not None else defaults["socket_sndbuf"],
        "co_correction": co_correction,
        "progress_interval": defaults["progress_interval"],
        "progress_enabled": progress_enabled,
        "label": args.label if args.label is not None else defaults["label"],
        "sla_path": args.sla if getattr(args, "sla", None) is not None else defaults["sla_path"],
        "fail_on_sla": args.fail_on_sla or defaults["fail_on_sla"],
        "pdf_report": args.pdf_report if args.pdf_report is not None else defaults["pdf_report"],
        "authorized_target": authorized_target,
    }
    return normalize_test_values(values)


def build_server_config(args: argparse.Namespace, config_data: dict[str, Any]) -> ServerConfig:
    defaults: dict[str, Any] = {"bind": "127.0.0.1", "port": 9999, "log_level": "INFO"}
    defaults.update(get_config_section(config_data, "server"))
    return ServerConfig(
        bind=str(args.bind if args.bind is not None else defaults["bind"]),
        port=int(args.port if args.port is not None else defaults["port"]),
        log_level=str(args.log_level if args.log_level is not None else defaults["log_level"]),
        max_packet_size=int(
            args.max_packet_size if args.max_packet_size is not None else defaults.get("max_packet_size", 65_507)
        ),
        rate_limit=float(args.rate_limit if args.rate_limit is not None else defaults.get("rate_limit", 0.0)),
    )


def build_monitor_config(args: argparse.Namespace, config_data: dict[str, Any]) -> MonitorConfig:
    defaults: dict[str, Any] = {
        "bind": "0.0.0.0",
        "http_port": 8888,
        "interval": 30,
        "history_limit": 100,
        "log_level": "INFO",
    }
    defaults.update(get_config_section(config_data, "monitor"))
    return MonitorConfig(
        bind=str(args.bind if args.bind is not None else defaults["bind"]),
        http_port=int(cast(Any, args.http_port if args.http_port is not None else defaults["http_port"])),
        interval=int(cast(Any, args.interval if args.interval is not None else defaults["interval"])),
        history_limit=int(cast(Any, defaults.get("history_limit", 100))),
        log_level=str(args.log_level if args.log_level is not None else defaults["log_level"]),
        stale_after_seconds=int(cast(Any, defaults.get("stale_after_seconds", 60))),
        state_file=str(defaults.get("state_file", "")),
        auth_token_file=str(defaults.get("auth_token_file", "")),
        health_requires_auth=coerce_bool(defaults.get("health_requires_auth", False)),
        tls_cert_file=str(defaults.get("tls_cert_file", "")),
        tls_key_file=str(defaults.get("tls_key_file", "")),
    )


def render_stats(stats: LatencyStats, *, use_rich: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps(stats.to_dict(), indent=2, sort_keys=True))
        return
    if use_rich and RICH_AVAILABLE and console is not None:
        from rich.table import Table

        table = Table(title=f"Neural Blitz Results: {stats.label}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for metric in (
            "success_rate",
            "loss_rate",
            "count_received",
            "count_lost",
            "mean_us",
            "p95_us",
            "p99_us",
            "jitter_us",
            "pps",
            "duration_s",
        ):
            value = getattr(stats, metric)
            rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
            table.add_row(metric, rendered)
        console.print(table)
        return
    print(json.dumps(stats.to_dict(), indent=2))


def render_comparison(
    baseline: LatencyStats,
    candidate: LatencyStats,
    rows: list[dict[str, Any]],
    *,
    use_rich: bool,
    as_json: bool,
    failures: list[str] | None = None,
) -> None:
    payload = {
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "comparison": rows,
        "failures": failures or [],
        "passed": not failures,
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if use_rich and RICH_AVAILABLE and console is not None:
        from rich.table import Table

        table = Table(title=f"Comparison: {baseline.label} → {candidate.label}")
        table.add_column("Metric")
        table.add_column("Baseline", justify="right")
        table.add_column("Candidate", justify="right")
        table.add_column("Delta", justify="right")
        for row in rows:
            delta_pct = "n/a" if row["delta_pct"] is None else f"{row['delta_pct']:.2f}%"
            table.add_row(
                row["metric"],
                f"{row['baseline']:.3f}",
                f"{row['candidate']:.3f}",
                f"{row['delta']:+.3f} ({delta_pct})",
            )
        console.print(table)
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
        return
    print(json.dumps(payload, indent=2))


def render_sla_result(failures: list[str], sla_path: str, *, use_rich: bool) -> None:
    if not failures:
        if use_rich and RICH_AVAILABLE and console is not None:
            from rich.panel import Panel

            console.print(Panel.fit(f"SLA PASS: {sla_path}", style="green"))
        else:
            print(f"SLA PASS: {sla_path}")
        return
    message = "\n".join(f"- {f}" for f in failures)
    if use_rich and RICH_AVAILABLE and error_console is not None:
        from rich.panel import Panel

        error_console.print(Panel.fit(f"SLA FAIL: {sla_path}\n{message}", style="red"))
    else:
        print(f"SLA FAIL: {sla_path}\n{message}", file=sys.stderr)


def render_batch_results(results: list[LatencyStats], *, use_rich: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return
    if use_rich and RICH_AVAILABLE and console is not None:
        from rich.table import Table

        table = Table(title="Batch Results")
        table.add_column("Label")
        table.add_column("Success", justify="right")
        table.add_column("P95 us", justify="right")
        table.add_column("P99 us", justify="right")
        for result in results:
            table.add_row(
                result.label,
                f"{result.success_rate:.2f}%",
                f"{result.p95_us:.2f}",
                f"{result.p99_us:.2f}",
            )
        console.print(table)
        return
    print(json.dumps([r.to_dict() for r in results], indent=2))


def _apply_authorized_flag(config_data: dict[str, Any], targets_data: dict[str, Any], authorized: bool) -> None:
    if not authorized:
        return
    test_section = targets_data.setdefault("test", {})
    if isinstance(test_section, dict):
        test_section["authorized_target"] = True


def execute_test(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_test_config(args, config_data)
    validate_test_config(config)
    configure_logging(config.log_level, use_rich)
    install_event_loop_policy()
    stats = asyncio.run(run_test(config, use_rich=use_rich and not args.json))
    render_stats(stats, use_rich=use_rich, as_json=args.json)
    if config.metrics_output:
        write_metrics(stats, config.metrics_output)
    sla_failures: list[str] | None = None
    if config.sla_path:
        sla_failures = evaluate_sla(stats, load_sla(config.sla_path))
        render_sla_result(sla_failures, config.sla_path, use_rich=use_rich)
    if config.pdf_report:
        write_pdf_report(stats, config, config.pdf_report, sla_failures)
    if sla_failures and config.fail_on_sla:
        return EXIT_SLA_FAILURE
    return EXIT_SUCCESS if stats.success_rate > 0 else EXIT_RUNTIME_ERROR


def execute_server(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_server_config(args, config_data)
    validate_server_config(config)
    configure_logging(config.log_level, use_rich)
    install_event_loop_policy()
    try:
        asyncio.run(
            run_server(
                config.bind,
                config.port,
                max_packet_size=config.max_packet_size,
                rate_limit=config.rate_limit,
            )
        )
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    return EXIT_SUCCESS


def execute_compare(args: argparse.Namespace, use_rich: bool) -> int:
    configure_logging(args.log_level, use_rich)
    baseline = load_metrics(args.baseline)
    candidate = load_metrics(args.candidate)
    if not baseline.label:
        baseline.label = "baseline"
    if not candidate.label:
        candidate.label = "candidate"
    rows = compare_stats(baseline, candidate)
    thresholds = ComparisonThresholds(
        max_p95_regression_pct=args.max_p95_regression,
        max_p99_regression_pct=args.max_p99_regression,
        max_loss_regression_pct=args.max_loss_regression,
        max_success_regression_pct=args.max_success_regression,
    )
    failures = evaluate_comparison(baseline, candidate, thresholds)
    render_comparison(baseline, candidate, rows, use_rich=use_rich, as_json=args.json, failures=failures)
    payload = {
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "comparison": rows,
        "failures": failures,
        "passed": not failures,
    }
    if args.output:
        write_comparison_output(args.output, payload)
    if failures and args.fail_on_regression:
        return EXIT_COMPARISON_FAILURE
    return EXIT_SUCCESS


def execute_batch(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    configure_logging(args.log_level, use_rich)
    install_event_loop_policy()
    targets_data = load_targets_file(args.targets_file)
    _apply_authorized_flag(config_data, targets_data, getattr(args, "i_understand_authorized_target", False))
    results = asyncio.run(
        run_batch_tests(
            config_data,
            targets_data,
            metrics_output=args.output,
            pdf_dir=args.pdf_dir,
            use_rich=use_rich and not args.json,
        )
    )
    render_batch_results(results, use_rich=use_rich, as_json=args.json)
    return EXIT_SUCCESS if results else EXIT_RUNTIME_ERROR


def execute_monitor(args: argparse.Namespace, config_data: dict[str, Any], use_rich: bool) -> int:
    config = build_monitor_config(args, config_data)
    validate_monitor_config(config)
    configure_logging(config.log_level, use_rich)
    install_event_loop_policy()
    targets_data = load_targets_file(args.targets_file)
    _apply_authorized_flag(config_data, targets_data, getattr(args, "i_understand_authorized_target", False))
    try:
        asyncio.run(run_monitor_loop(config_data, args.targets_file, config, use_rich=False))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    return EXIT_SUCCESS


def execute_validate_config(args: argparse.Namespace) -> int:
    errors = validate_config_file(args.path)
    if args.json:
        print(json.dumps({"path": args.path, "valid": not errors, "errors": errors}, indent=2))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(f"Config valid: {args.path}")
    return EXIT_CONFIG_ERROR if errors else EXIT_SUCCESS


def execute_validate_sla(args: argparse.Namespace) -> int:
    try:
        sla = load_sla(args.path)
        errors = validate_sla_config(sla)
    except (ConfigError, DependencyMissing) as exc:
        errors = [str(exc)]
    if args.json:
        print(json.dumps({"path": args.path, "valid": not errors, "errors": errors}, indent=2))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(f"SLA valid: {args.path}")
    return EXIT_CONFIG_ERROR if errors else EXIT_SUCCESS


def execute_version(args: argparse.Namespace) -> int:
    payload = {"name": APP_NAME, "version": __version__}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{APP_NAME} {__version__}")
    return EXIT_SUCCESS


def execute_init_config(args: argparse.Namespace, use_rich: bool) -> int:
    write_sample_config(args.output)
    message = f"Sample config written to {Path(args.output).expanduser()}"
    if use_rich and RICH_AVAILABLE and console is not None:
        from rich.panel import Panel

        console.print(Panel.fit(message, style="green"))
    else:
        print(message)
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config_data = load_config(args.config)
        use_rich = not getattr(args, "no_rich", False) and RICH_AVAILABLE
        handlers = {
            "test": lambda: execute_test(args, config_data, use_rich),
            "server": lambda: execute_server(args, config_data, use_rich),
            "compare": lambda: execute_compare(args, use_rich),
            "batch": lambda: execute_batch(args, config_data, use_rich),
            "monitor": lambda: execute_monitor(args, config_data, use_rich),
            "validate-config": lambda: execute_validate_config(args),
            "validate-sla": lambda: execute_validate_sla(args),
            "version": lambda: execute_version(args),
            "init-config": lambda: execute_init_config(args, use_rich),
        }
        handler = handlers.get(args.command)
        if handler is None:
            raise ConfigError(f"Unsupported command: {args.command}")
        return handler()
    except SafetyViolation as exc:
        emit_error(str(exc), use_rich=RICH_AVAILABLE)
        return EXIT_SAFETY_VIOLATION
    except ConfigError as exc:
        emit_error(str(exc), use_rich=RICH_AVAILABLE)
        return EXIT_CONFIG_ERROR
    except DependencyMissing as exc:
        emit_error(str(exc), use_rich=RICH_AVAILABLE)
        return EXIT_DEPENDENCY_MISSING
    except ComparisonFailure as exc:
        emit_error(str(exc), use_rich=RICH_AVAILABLE)
        return EXIT_COMPARISON_FAILURE
    except (MetricsError, NeuralBlitzError) as exc:
        emit_error(str(exc), use_rich=RICH_AVAILABLE)
        return EXIT_RUNTIME_ERROR
    except KeyboardInterrupt:
        emit_error("Interrupted", use_rich=RICH_AVAILABLE)
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover - safety net
        import logging

        logging.getLogger("neural_blitz").exception("Unexpected error")
        emit_error(f"Unexpected error: {exc}", use_rich=RICH_AVAILABLE)
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
