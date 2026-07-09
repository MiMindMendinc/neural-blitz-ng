# Metrics

Neural Blitz NG records per-run latency and reliability metrics.

## Core fields

| Field | Description |
| ----- | ----------- |
| `count_sent` / `count_received` / `count_lost` | Packet counters |
| `count_retried` / `count_duplicate` / `count_malformed` | Quality counters |
| `success_rate` / `loss_rate` | Percentages |
| `min_us` … `p9999_us` | Latency percentiles (microseconds) |
| `co_p50_us` … `co_p999_us` | Coordinated-omission corrected percentiles |
| `jitter_us` | Mean adjacent RTT delta |
| `pps` | Packets per second |
| `host` / `port` / `label` | Target identity |
| `timestamp_utc` / `version` | Run metadata |

## Export formats

```bash
neural-blitz test ... --metrics-output metrics/latest.json
neural-blitz test ... --metrics-output metrics/latest.csv
```

JSON is pretty-printed and sorted for stable diffs. CSV uses stable column headers.

## Monitor endpoints

- `GET /metrics` — JSON map of latest stats per target
- `GET /api/targets` — target labels
- `GET /api/target/{label}` — bounded history per target
