# Prometheus Integration

Monitor mode exposes Prometheus text at `/metrics/prometheus`.

## Scrape config

See `examples/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: neural-blitz
    metrics_path: /metrics/prometheus
    static_configs:
      - targets: ['127.0.0.1:8888']
```

## Metric names

| Metric | Type | Labels |
| ------ | ---- | ------ |
| `neural_blitz_success_rate_percent` | gauge | label, host, port |
| `neural_blitz_loss_rate_percent` | gauge | label, host, port |
| `neural_blitz_latency_p50_us` | gauge | label, host, port |
| `neural_blitz_latency_p95_us` | gauge | label, host, port |
| `neural_blitz_latency_p99_us` | gauge | label, host, port |
| `neural_blitz_jitter_us` | gauge | label, host, port |
| `neural_blitz_packets_sent_total` | counter-like gauge | label, host, port |
| `neural_blitz_packets_received_total` | counter-like gauge | label, host, port |
| `neural_blitz_packets_lost_total` | counter-like gauge | label, host, port |
| `neural_blitz_target_up` | gauge | label, host, port |
| `neural_blitz_last_run_timestamp_seconds` | gauge | label, host, port |

Cardinality is intentionally limited to `label`, `host`, and `port`.

The endpoint emits Prometheus `HELP` and `TYPE` metadata and escapes all label
values. `neural_blitz_last_run_timestamp_seconds` is a numeric Unix timestamp,
so it can be used directly in PromQL.

## Health and target state

`/health` returns `200` only when every configured target is current and
healthy. It returns `503` with per-target states (`ok`, `degraded`, `stale`,
`failed`, or `never_run`) otherwise. Use `/api/target/{label}/status` for the
last error and consecutive-failure count; the original history endpoint remains
at `/api/target/{label}`.

## Grafana

Import `examples/grafana-dashboard.json` as a starting dashboard.
