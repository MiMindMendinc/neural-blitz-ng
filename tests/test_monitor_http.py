"""Monitor HTTP endpoint tests."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from neural_blitz.metrics import LatencyStats
from neural_blitz.monitor import TargetState, build_monitor_app


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


@pytest.mark.integration
async def test_monitor_bearer_auth_and_degraded_health():
    latest = {"local": LatencyStats(label="local", success_rate=0.0)}
    app = build_monitor_app(latest, {"local": []}, auth_token="secret")
    async with TestClient(TestServer(app)) as client:
        assert (await client.get("/metrics")).status == 401
        assert (await client.get("/health")).status == 503
        authorized = await client.get("/metrics", headers={"Authorization": "Bearer secret"})
        assert authorized.status == 200
        status = await client.get("/api/target/local/status", headers={"Authorization": "Bearer secret"})
        assert (await status.json())["status"] in {"degraded", "ok"}


@pytest.mark.integration
async def test_monitor_http_returns_json_404_for_unknown_target_endpoints():
    app = build_monitor_app({}, {}, states={"failed": TargetState(last_error="timeout")})
    async with TestClient(TestServer(app)) as client:
        for endpoint in ("/api/target/missing", "/api/target/missing/status"):
            response = await client.get(endpoint)
            assert response.status == 404
            assert await response.json() == {"error": "unknown target"}


@pytest.mark.unit
def test_target_state_transitions():
    state = TargetState()
    assert state.status(60, now=100.0) == "never_run"
    state.last_error = "timeout"
    assert state.status(60, now=100.0) == "failed"
    state.latest = LatencyStats(success_rate=100.0)
    state.last_success_at = 100.0
    assert state.status(60, now=101.0) == "degraded"
    state.last_error = None
    assert state.status(60, now=101.0) == "ok"
    assert state.status(60, now=161.0) == "stale"


@pytest.mark.unit
def test_target_state_failure_statuses_without_successful_result():
    failed = TargetState(last_error="timed out", consecutive_failures=2)
    degraded = TargetState(
        latest=LatencyStats(success_rate=0.0),
        last_success_at=100.0,
        last_error="packet loss",
        consecutive_failures=1,
    )

    assert failed.status(60, now=100.0) == "failed"
    assert degraded.status(60, now=101.0) == "degraded"
