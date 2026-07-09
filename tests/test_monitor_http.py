"""Monitor HTTP endpoint tests."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import build_monitor_app


@pytest.mark.integration
async def test_monitor_http_endpoints():
    latest = {
        "local": LatencyStats(
            label="local",
            host="127.0.0.1",
            port=9999,
            success_rate=99.0,
            p95_us=100.0,
            count_sent=10,
            count_received=10,
        )
    }
    history = {"local": [latest["local"].to_dict()]}
    app = build_monitor_app(latest, history)
    async with TestClient(TestServer(app)) as client:
        health = await client.get("/health")
        assert health.status == 200
        payload = await health.json()
        assert payload["status"] == "ok"
        assert payload["targets"] == 1

        prom = await client.get("/metrics/prometheus")
        text = await prom.text()
        assert "neural_blitz_success_rate_percent" in text

        metrics = await client.get("/metrics")
        data = await metrics.json()
        assert "local" in data

        targets = await client.get("/api/targets")
        assert await targets.json() == ["local"]

        hist = await client.get("/api/target/local")
        assert len(await hist.json()) == 1
