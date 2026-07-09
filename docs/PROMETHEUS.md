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
| `neural_blitz_last_run_timestamp` | info | label, host, port |

Cardinality is intentionally limited to `label`, `host`, and `port`.

## Grafana

Import `examples/grafana-dashboard.json` as a starting dashboard.
