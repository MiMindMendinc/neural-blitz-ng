"""Continuous monitoring with HTTP endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import signal
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neural_blitz.config import MonitorConfig, build_test_config_from_overrides, load_targets_file
from neural_blitz.constants import __version__
from neural_blitz.errors import DependencyMissing
from neural_blitz.metrics import LatencyStats, write_metrics
from neural_blitz.prometheus import format_prometheus_metrics
from neural_blitz.report_pdf import write_pdf_report
from neural_blitz.sla import evaluate_sla, load_sla
from neural_blitz.udp_client import run_test

logger = logging.getLogger("neural_blitz")


@dataclass
class TargetState:
    """Runtime state that remains useful when a target temporarily fails."""

    latest: LatencyStats | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    last_success_at: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0

    def status(self, stale_after_seconds: int, now: float | None = None) -> str:
        now = time.time() if now is None else now
        if self.last_success_at is None:
            return "failed" if self.last_error else "never_run"
        if now - self.last_success_at > stale_after_seconds:
            return "stale"
        if self.last_error or self.latest is None or self.latest.success_rate <= 0:
            return "degraded"
        return "ok"


def _atomic_json_write(path: str, data: dict[str, Any]) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


async def run_batch_tests(
    config_data: dict[str, Any],
    targets_data: dict[str, Any],
    *,
    metrics_output: str | None = None,
    pdf_dir: str | None = None,
    use_rich: bool = False,
    failures: dict[str, str] | None = None,
) -> list[LatencyStats]:
    from pathlib import Path

    shared_overrides = targets_data.get("test", {})
    base_dir = Path(str(targets_data.get("__base_dir", Path.cwd())))
    if shared_overrides and not isinstance(shared_overrides, dict):
        from neural_blitz.errors import ConfigError

        raise ConfigError("Targets file key 'test' must be a mapping")
    results: list[LatencyStats] = []
    for index, target in enumerate(targets_data["targets"]):
        if not isinstance(target, dict):
            from neural_blitz.errors import ConfigError

            raise ConfigError("Each target entry must be a mapping")
        label = target.get("label") or target.get("name") or f"target-{index + 1}"
        overrides = dict(shared_overrides or {})
        overrides.update(target)
        overrides["label"] = label
        overrides["progress_enabled"] = False
        for path_key in ("metrics_output", "pdf_report", "sla_path", "sla"):
            path_value = overrides.get(path_key)
            if path_key == "sla" and path_value and "sla_path" not in overrides:
                overrides["sla_path"] = path_value
            path_value = overrides.get(path_key if path_key != "sla" else "sla_path")
            if isinstance(path_value, str) and path_value and not Path(path_value).is_absolute():
                overrides[path_key if path_key != "sla" else "sla_path"] = str(base_dir / path_value)
        if pdf_dir:
            overrides["pdf_report"] = str(Path(pdf_dir).expanduser() / f"{label}.pdf")
        batch_config = build_test_config_from_overrides(config_data, overrides)
        from neural_blitz.config import validate_test_config

        validate_test_config(batch_config)
        logger.info("Batch target %s -> %s:%d", batch_config.label, batch_config.host, batch_config.port)
        try:
            stats = await run_test(batch_config, use_rich=use_rich)
            results.append(stats)
            if batch_config.metrics_output:
                write_metrics(stats, batch_config.metrics_output)
            if batch_config.pdf_report:
                sla_failures = None
                if batch_config.sla_path:
                    sla_failures = evaluate_sla(stats, load_sla(batch_config.sla_path))
                write_pdf_report(stats, batch_config, batch_config.pdf_report, sla_failures)
        except Exception as exc:
            logger.error("Target %s failed: %s", label, exc)
            if failures is not None:
                failures[str(label)] = str(exc)
    if metrics_output:
        import json
        from pathlib import Path

        destination = Path(metrics_output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            json.dump([r.to_dict() for r in results], handle, indent=2, sort_keys=True)
            handle.write("\n")
    return results


def build_monitor_app(
    latest: dict[str, LatencyStats],
    history: dict[str, list[dict[str, Any]]],
    *,
    states: dict[str, TargetState] | None = None,
    stale_after_seconds: int = 60,
    auth_token: str = "",
    health_requires_auth: bool = False,
) -> Any:
    from aiohttp import web

    states = (
        states
        if states is not None
        else {
            label: TargetState(latest=stats, history=history.get(label, []), last_success_at=time.time())
            for label, stats in latest.items()
        }
    )

    @web.middleware
    async def authentication(request: web.Request, handler: Any) -> web.StreamResponse:
        if not auth_token or (request.path == "/health" and not health_requires_auth):
            return await handler(request)
        provided = request.headers.get("Authorization", "")
        expected = f"Bearer {auth_token}"
        if not hmac.compare_digest(provided, expected):
            return web.json_response(
                {"error": "authentication required"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await handler(request)

    async def metrics_json(_: web.Request) -> web.Response:
        return web.json_response({label: stats.to_dict() for label, stats in latest.items()})

    async def metrics_prometheus(_: web.Request) -> web.Response:
        return web.Response(text=format_prometheus_metrics(latest), content_type="text/plain; version=0.0.4")

    async def health(_: web.Request) -> web.Response:
        statuses = {label: state.status(stale_after_seconds) for label, state in states.items()}
        healthy = sum(1 for status in statuses.values() if status == "ok")
        status = "ok" if statuses and healthy == len(statuses) else "degraded"
        return web.json_response(
            {
                "status": status,
                "version": __version__,
                "targets": len(states),
                "healthy_targets": healthy,
                "target_status": statuses,
            },
            status=200 if status == "ok" else 503,
        )

    async def api_targets(_: web.Request) -> web.Response:
        return web.json_response(sorted(states.keys()))

    async def api_target(request: web.Request) -> web.Response:
        label = request.match_info["label"]
        state = states.get(label)
        if state is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "unknown target"}), content_type="application/json")
        return web.json_response(state.history)

    async def api_target_status(request: web.Request) -> web.Response:
        label = request.match_info["label"]
        state = states.get(label)
        if state is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "unknown target"}), content_type="application/json")
        return web.json_response(
            {
                "status": state.status(stale_after_seconds),
                "last_error": state.last_error,
                "consecutive_failures": state.consecutive_failures,
            }
        )

    app = web.Application(middlewares=[authentication])
    app.router.add_get("/metrics", metrics_json)
    app.router.add_get("/metrics/prometheus", metrics_prometheus)
    app.router.add_get("/health", health)
    app.router.add_get("/api/targets", api_targets)
    app.router.add_get("/api/target/{label}", api_target)
    app.router.add_get("/api/target/{label}/status", api_target_status)
    return app


async def run_monitor_loop(
    config_data: dict[str, Any],
    targets_file: str,
    monitor_config: MonitorConfig,
    *,
    use_rich: bool = False,
) -> None:
    try:
        from aiohttp import web
    except ImportError as exc:
        raise DependencyMissing("Monitor mode requires aiohttp. Install with: pip install aiohttp") from exc

    latest: dict[str, LatencyStats] = {}
    history: dict[str, list[dict[str, Any]]] = {}
    states: dict[str, TargetState] = {}
    shutdown = asyncio.Event()
    auth_token = ""
    if monitor_config.auth_token_file:
        try:
            auth_token = Path(monitor_config.auth_token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise DependencyMissing(f"Unable to read monitor auth token file: {exc}") from exc
        if not auth_token:
            raise DependencyMissing("Monitor auth token file is empty")

    async def run_cycle() -> None:
        targets_data = load_targets_file(targets_file)
        targets_data.setdefault("test", {})
        cycle_failures: dict[str, str] = {}
        results = await run_batch_tests(config_data, targets_data, use_rich=use_rich, failures=cycle_failures)
        configured_labels = {
            str(target.get("label") or target.get("name") or f"target-{index + 1}")
            for index, target in enumerate(targets_data["targets"])
            if isinstance(target, dict)
        }
        for label in configured_labels:
            states.setdefault(label, TargetState())
        for label, error in cycle_failures.items():
            state = states.setdefault(label, TargetState())
            state.last_error = error
            state.consecutive_failures += 1
        for result in results:
            latest[result.label] = result
            hist = history.setdefault(result.label, [])
            hist.append(result.to_dict())
            if len(hist) > monitor_config.history_limit:
                del hist[: len(hist) - monitor_config.history_limit]
            state = states.setdefault(result.label, TargetState())
            state.latest = result
            state.history = hist
            state.last_success_at = time.time()
            state.last_error = None
            state.consecutive_failures = 0
        if monitor_config.state_file:
            _atomic_json_write(
                monitor_config.state_file,
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "targets": {
                        label: {
                            "status": state.status(monitor_config.stale_after_seconds),
                            "last_error": state.last_error,
                            "consecutive_failures": state.consecutive_failures,
                            "latest": state.latest.to_dict() if state.latest else None,
                        }
                        for label, state in states.items()
                    },
                },
            )
        logger.info("Monitor cycle complete: %d target(s)", len(results))

    app = build_monitor_app(
        latest,
        history,
        states=states,
        stale_after_seconds=monitor_config.stale_after_seconds,
        auth_token=auth_token,
        health_requires_auth=monitor_config.health_requires_auth,
    )

    runner = web.AppRunner(app)
    await runner.setup()
    ssl_context: ssl.SSLContext | None = None
    if monitor_config.tls_cert_file:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(monitor_config.tls_cert_file, monitor_config.tls_key_file)
    site = web.TCPSite(runner, monitor_config.bind, monitor_config.http_port, ssl_context=ssl_context)
    await site.start()
    logger.info("Monitor HTTP listening on %s:%d", monitor_config.bind, monitor_config.http_port)

    loop = asyncio.get_running_loop()

    def on_signal() -> None:
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, on_signal)

    try:
        while not shutdown.is_set():
            try:
                await run_cycle()
            except Exception as exc:
                logger.error("Monitor cycle failed: %s", exc)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=monitor_config.interval)
                break
            except asyncio.TimeoutError:
                continue
    finally:
        await runner.cleanup()
