# Neural Blitz NG

**Production-oriented UDP latency benchmarking and monitoring for small teams, nonprofits, local-first operators, and practical network maintainers.**

Neural Blitz NG is a lightweight command-line tool for measuring UDP latency, packet loss, jitter, and service-level thresholds without enterprise monitoring complexity. It is built by Michigan MindMend Inc. for operators who need clear network visibility, simple deployment, and auditable local metrics.

## Core capabilities

- Single-run UDP latency and packet-loss testing
- Local UDP echo server mode
- Batch multi-target benchmarking from YAML
- Continuous monitor mode with HTTP metrics
- Prometheus-compatible metrics endpoint
- JSON and CSV metrics exports
- PDF report generation
- SLA threshold checks
- Metrics comparison workflows
- Rich terminal output and progress bars
- Docker and Docker Compose deployment

## Install

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e .
```

Or install dependencies directly when running the single-file script:

```bash
python -m pip install aiohttp pyyaml reportlab rich
```

## Quick start

Start a local UDP echo server:

```bash
neural-blitz server --bind 127.0.0.1 --port 9999
```

Run a test against it:

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --count 10000 --concurrency 200 --rate 5000
```

Write metrics and a PDF report:

```bash
neural-blitz test \
  --host 127.0.0.1 \
  --port 9999 \
  --metrics-output metrics/latest.json \
  --pdf-report reports/latest.pdf
```

Run a batch test from YAML:

```bash
neural-blitz batch --targets-file neural_blitz.yaml --output metrics/batch.json
```

Run continuous monitor mode:

```bash
neural-blitz monitor --targets-file neural_blitz.yaml --http-port 8888 --interval 30
```

## Docker

Build and run with Docker Compose:

```bash
docker compose up --build
```

Then open:

- `http://127.0.0.1:8888/health`
- `http://127.0.0.1:8888/metrics`
- `http://127.0.0.1:8888/metrics/prometheus`

## Configuration

`neural_blitz.yaml` can define defaults, test settings, monitor settings, and target groups.

Example target block:

```yaml
targets:
  - label: hq
    host: 127.0.0.1
    port: 9999
  - label: branch
    host: 127.0.0.1
    port: 9998
```

## SLA checks

`sla.yaml` supports threshold keys such as:

```yaml
min_success_rate: 99.9
max_p95_us: 1500.0
max_p99_us: 2500.0
max_jitter_us: 500.0
min_pps: 1000.0
```

Use SLA checks to fail a run when a target falls below your required reliability threshold.

## Metrics endpoints

Monitor mode exposes:

- `/health` health status
- `/metrics` JSON metrics
- `/metrics/prometheus` Prometheus text format
- `/api/targets` target labels
- `/api/target/<label>` target history

## Michigan MindMend ecosystem

Neural Blitz NG can serve as a lightweight monitoring layer for local-first infrastructure, Sentinel-style safety stacks, nonprofit deployments, edge AI labs, and small service-provider environments where simple network proof matters.

## Development status

This repo is an active production-oriented build. The core CLI and monitoring workflow are present, with tests and CI included to keep future changes honest.

## License

MIT License. See `LICENSE` for details.
