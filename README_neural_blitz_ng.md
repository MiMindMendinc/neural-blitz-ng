# Neural Blitz NG

Neural Blitz NG is a production-ready UDP latency tester and echo server with:

- async UDP benchmark and echo server modes
- batch multi-target testing
- continuous monitor mode with HTTP metrics
- coordinated omission correction
- retries, warmup, rate limiting, and metrics export
- rich terminal output with progress bars
- YAML config support
- PDF report generation
- SLA evaluation
- metrics comparison mode

## Install

```bash
pip install .
```

Or install editable during development:

```bash
pip install -e .
```

## Quick Start

Start a server:

```bash
neural-blitz server --port 9999
```

Run a test:

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --count 10000 --concurrency 200 --rate 5000
```

Initialize a sample config:

```bash
neural-blitz init-config --output neural_blitz.yaml
```

Run with a config:

```bash
neural-blitz --config neural_blitz.yaml test

Generate a PDF report after a run:

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --pdf-report reports/latest.pdf
```
```

Compare two results:

```bash
neural-blitz compare --baseline metrics/baseline.json --candidate metrics/latest.json

Run a batch from a targets file:

```bash
neural-blitz batch --targets-file targets.yaml --output metrics/batch.json
```

Run continuous monitor mode:

```bash
neural-blitz monitor --targets-file targets.yaml --http-port 8888 --interval 30
```
```

## Metrics

Metrics can be written as JSON or CSV with `--metrics-output`.

PDF reports can be written with `--pdf-report` and include a formatted summary of the run.

Monitor mode exposes:

- `/metrics` JSON
- `/metrics/prometheus` Prometheus text format
- `/health` health status
- `/api/targets` target labels
- `/api/target/<label>` target history

## SLA

Point `--sla` at a YAML file containing threshold keys such as:

- `min_success_rate`
- `max_mean_us`
- `max_p95_us`
- `max_p99_us`
- `max_p999_us`
- `max_co_p99_us`
- `max_jitter_us`
- `min_pps`

Use `--fail-on-sla` to exit non-zero when a run violates the SLA.
