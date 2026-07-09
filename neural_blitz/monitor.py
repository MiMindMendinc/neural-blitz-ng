"""Continuous monitoring with HTTP endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
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


async def run_batch_tests(
    config_data: dict[str, Any],
    targets_data: dict[str, Any],
    *,
    metrics_output: str | None = None,
    pdf_dir: str | None = None,
    use_rich: bool = False,
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
) -> Any:
    from aiohttp import web

    async def metrics_json(_: web.Request) -> web.Response:
        return web.json_response({label: stats.to_dict() for label, stats in latest.items()})

    async def metrics_prometheus(_: web.Request) -> web.Response:
        return web.Response(text=format_prometheus_metrics(latest), content_type="text/plain; version=0.0.4")

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "version": __version__,
                "targets": len(latest),
                "healthy_targets": sum(1 for s in latest.values() if s.success_rate > 0),
            }
        )

    async def api_targets(_: web.Request) -> web.Response:
        return web.json_response(sorted(latest.keys()))

    async def api_target(request: web.Request) -> web.Response:
        label = request.match_info["label"]
        return web.json_response(history.get(label, []))

    app = web.Application()
    app.router.add_get("/metrics", metrics_json)
    app.router.add_get("/metrics/prometheus", metrics_prometheus)
    app.router.add_get("/health", health)
    app.router.add_get("/api/targets", api_targets)
    app.router.add_get("/api/target/{label}", api_target)
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
    shutdown = asyncio.Event()

    async def run_cycle() -> None:
        targets_data = load_targets_file(targets_file)
        targets_data.setdefault("test", {})
        results = await run_batch_tests(config_data, targets_data, use_rich=use_rich)
        for result in results:
            latest[result.label] = result
            hist = history.setdefault(result.label, [])
            hist.append(result.to_dict())
            if len(hist) > monitor_config.history_limit:
                del hist[: len(hist) - monitor_config.history_limit]
        logger.info("Monitor cycle complete: %d target(s)", len(results))

    app = build_monitor_app(latest, history)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, monitor_config.bind, monitor_config.http_port)
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
