# Neural Blitz NG

Neural Blitz NG is a production-ready UDP network latency benchmarking and monitoring tool built by Michigan MindMend Inc.

It is designed for nonprofits, small businesses, and service providers that need practical network visibility without enterprise complexity.

## Included

- `neural_blitz_ng.py`
  Main application with `test`, `server`, `batch`, and `monitor` modes
- `Dockerfile`
  Container image for monitor deployment
- `docker-compose.yml`
  One-command container deployment
- `neural_blitz.yaml`
  Sample configuration and targets file
- `sla.yaml`
  Sample SLA thresholds
- `Neural_Blitz_NG_One_Pager.pdf`
  Sales and partner-facing overview

## Core Capabilities

- Single-run latency and packet-loss testing
- Batch multi-target benchmarking from YAML
- PDF report generation
- Monitor mode with HTTP metrics
- Prometheus-compatible endpoint
- JSON and CSV metrics exports
- SLA checking and comparison workflows

## Quick Start

Install locally:

```powershell
python -m pip install aiohttp pyyaml reportlab rich
```

Run a local echo server:

```powershell
python neural_blitz_ng.py server --bind 127.0.0.1 --port 9999
```

Run a test:

```powershell
python neural_blitz_ng.py test --host 127.0.0.1 --port 9999 --metrics-output metrics\latest.json --pdf-report reports\latest.pdf
```

Run a batch test:

```powershell
python neural_blitz_ng.py batch --targets-file neural_blitz.yaml --output batch_results.json
```

Run monitor mode:

```powershell
python neural_blitz_ng.py monitor --targets-file neural_blitz.yaml --http-port 8888 --interval 30
```

## Docker

Build and run with Docker Compose:

```powershell
docker compose up --build
```

Then open:

- `http://127.0.0.1:8888/health`
- `http://127.0.0.1:8888/metrics`
- `http://127.0.0.1:8888/metrics/prometheus`

## Recommended Repo Additions

If you publish this to GitHub next, add:

- a license file
- a few benchmark screenshots or sample reports
- a short case study or sample output folder
- GitHub issue templates for bugs and feature requests
