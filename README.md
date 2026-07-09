# Neural Blitz NG

**Measure the link before the outage writes the story.**

[![CI](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/ci.yml/badge.svg)](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![Ruff](https://img.shields.io/badge/ruff-enabled-261230)
![Tests](https://img.shields.io/badge/tests-pytest-brightgreen)

Local-first UDP latency benchmarking and monitoring for nonprofits, small businesses, MSPs, homelab operators, rural connectivity projects, and edge AI infrastructure teams.

## What it does

Neural Blitz NG measures **UDP latency, packet loss, jitter, and SLA compliance** with a practical CLI, YAML configuration, Prometheus endpoints, and Docker deployment — without enterprise monitoring complexity.

## Why it exists

Small teams need answers fast:

- Is this link healthy?
- Are packets being dropped?
- Did latency regress after a change?
- Can we expose metrics to Prometheus?

Neural Blitz NG fills the gap between `ping` and a full observability platform.

## Quick start

```bash
pip install -e ".[dev,pdf]"

# Terminal 1 — echo server
neural-blitz server --bind 127.0.0.1 --port 9999

# Terminal 2 — latency test
neural-blitz test --host 127.0.0.1 --port 9999 --count 1000 --concurrency 50
```

## Install

```bash
pip install neural-blitz-ng
# optional PDF reports
pip install 'neural-blitz-ng[pdf]'
# optional uvloop on Linux/macOS
pip install 'neural-blitz-ng[uvloop]'
```

Development:

```bash
make dev
make test
```

## Commands

| Command | Description |
| ------- | ----------- |
| `neural-blitz server` | UDP echo server |
| `neural-blitz test` | Single-target latency test |
| `neural-blitz batch` | Multi-target YAML batch run |
| `neural-blitz monitor` | Continuous monitor + HTTP API |
| `neural-blitz compare` | Baseline vs candidate metrics |
| `neural-blitz validate-config` | Validate YAML config |
| `neural-blitz validate-sla` | Validate SLA YAML |
| `neural-blitz version` | Print version |
| `neural-blitz init-config` | Write sample config |

## Batch mode

```bash
neural-blitz batch --targets-file examples/neural_blitz.yaml --output metrics/batch.json
```

## Monitor mode

```bash
neural-blitz monitor --targets-file examples/neural_blitz.yaml --http-port 8888
curl http://127.0.0.1:8888/health
curl http://127.0.0.1:8888/metrics/prometheus
```

## Docker

```bash
docker compose up --build
```

See [docs/DOCKER.md](docs/DOCKER.md).

## Prometheus

Scrape `/metrics/prometheus` from monitor mode. Metric names use the `neural_blitz_*` prefix. See [docs/PROMETHEUS.md](docs/PROMETHEUS.md).

## SLA checks

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --sla examples/sla.yaml --fail-on-sla
```

Exit code `2` on SLA failure. See [docs/SLA.md](docs/SLA.md).

## PDF reports

```bash
pip install 'neural-blitz-ng[pdf]'
neural-blitz test --host 127.0.0.1 --port 9999 --pdf-report reports/latest.pdf
```

## Safety model

> **Authorized use only.** Default targets are localhost. Public or third-party hosts require `--i-understand-authorized-target`.

- Hard ceilings on count, concurrency, rate, and packet size
- No scanning, spoofing, or amplification features
- Responsible-use notice on test runs

Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) and [SECURITY.md](SECURITY.md).

## Example output

```text
╭─ Neural Blitz Results: local ─╮
│ success_rate    99.800        │
│ p95_us          142.500       │
│ p99_us          210.000       │
│ jitter_us       18.200        │
╰───────────────────────────────╯
```

## Project structure

```text
neural_blitz/          # Python package
tests/                 # pytest suite
docs/                  # operator documentation
examples/              # YAML, Prometheus, Grafana samples
.github/workflows/     # CI, CodeQL, release
```

## Roadmap

- [ ] Config hot-reload for monitor mode
- [ ] IPv6-first bind examples
- [ ] Helm chart for Kubernetes monitor deployments

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests welcome via GitHub issues.

## License

MIT — see [LICENSE](LICENSE).

## Michigan MindMend ecosystem

Built by **Michigan MindMend Inc.** for practical operators who need local-first infrastructure visibility — from nonprofit field sites to edge AI labs and small MSP footprints.
