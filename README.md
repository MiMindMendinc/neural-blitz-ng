<div align="center">

# Neural Blitz NG

### Measure the link before the outage writes the story.

**Local-first UDP latency benchmarking and monitoring for practical operators.**

[![CI](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/ci.yml/badge.svg)](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/ci.yml)
[![CodeQL](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/codeql.yml/badge.svg)](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/codeql.yml)
[![Release](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/release.yml/badge.svg)](https://github.com/MiMindMendinc/neural-blitz-ng/actions/workflows/release.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-9.0.0-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](docs/DOCKER.md)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/types-mypy-blue)](https://mypy-lang.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-86%25-brightgreen)](UPGRADE_REPORT.md)
[![Security](https://img.shields.io/badge/security-policy-blue)](SECURITY.md)
[![Contributing](https://img.shields.io/badge/contributing-welcome-0f766e)](CONTRIBUTING.md)
[![Code of Conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa)](CODE_OF_CONDUCT.md)

[Quick Start](#quick-start) ·
[Install](#install) ·
[Commands](#commands) ·
[Docker](#docker) ·
[Prometheus](#prometheus) ·
[Safety](#safety-model) ·
[Docs](docs/QUICKSTART.md) ·
[Changelog](CHANGELOG.md)

Built by **[Michigan MindMend Inc.](https://github.com/MiMindMendinc)** for nonprofits, small businesses, MSPs, homelabs, rural connectivity projects, and edge AI operators.

</div>

---

## What it does

Neural Blitz NG measures **UDP latency, packet loss, jitter, and SLA compliance** with a practical CLI, YAML configuration, Prometheus endpoints, PDF reports, and Docker deployment — without enterprise monitoring complexity.

| Capability | Description |
| ---------- | ----------- |
| UDP echo server | Local test target for repeatable benchmarks |
| Single-target test | Latency percentiles, loss, jitter, CO correction |
| Batch YAML mode | Multi-target runs from one config file |
| Monitor mode | Periodic tests + HTTP `/health` and `/metrics` |
| Prometheus | `neural_blitz_*` metrics for Grafana |
| SLA checks | Pass/fail thresholds with exit code `2` |
| Compare mode | Baseline vs candidate regression checks |
| PDF reports | Optional branded reports via `reportlab` |

## Why it exists

Small teams need answers fast:

- Is this link healthy?
- Are packets being dropped?
- Did latency regress after a change?
- Can we expose metrics to Prometheus?

Neural Blitz NG fills the gap between `ping` and a full observability platform.

## Quick start

```bash
git clone https://github.com/MiMindMendinc/neural-blitz-ng.git
cd neural-blitz-ng
pip install -e ".[dev,pdf]"
```

**Terminal 1 — echo server**

```bash
neural-blitz server --bind 127.0.0.1 --port 9999
```

**Terminal 2 — latency test**

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --count 1000 --concurrency 50
```

## Install

```bash
pip install neural-blitz-ng
pip install 'neural-blitz-ng[pdf]'      # PDF reports
pip install 'neural-blitz-ng[uvloop]'    # faster asyncio on Linux/macOS
pip install 'neural-blitz-ng[dev]'       # contributors
```

Development:

```bash
make dev
make lint
make test
make coverage
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

```bash
neural-blitz --help
python -m neural_blitz --help
```

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

Monitor probes have distinct meanings:

- `/live` returns `200` whenever the monitor HTTP process is accepting requests.
- `/ready` returns `200` once the targets file has been validated and a `never_run`
  state has been created for every configured target.
- `/health` reports downstream target health. It returns `200` only when every
  target has a recent successful result, otherwise `503`.

`/live`, `/ready`, and `/health` are available without a bearer token unless
`health_requires_auth` is enabled. Use `/live` or `/ready` for container
orchestrator probes; do not use downstream `/health` for process liveness.

## Docker

```bash
docker compose up --build
```

See [docs/DOCKER.md](docs/DOCKER.md).

## Prometheus

Scrape `/metrics/prometheus` from monitor mode. Metric names use the `neural_blitz_*` prefix.

See [docs/PROMETHEUS.md](docs/PROMETHEUS.md) and [examples/prometheus.yml](examples/prometheus.yml).

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
neural_blitz/          # Python package (CLI, UDP, metrics, monitor)
tests/                 # pytest suite (99 tests, 86% coverage)
docs/                  # operator documentation
examples/              # YAML, Prometheus, Grafana samples
.github/workflows/     # CI, CodeQL, release
```

## Documentation

| Doc | Topic |
| --- | ----- |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 5-minute local setup |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | YAML config reference |
| [docs/METRICS.md](docs/METRICS.md) | Metrics fields and export |
| [docs/SLA.md](docs/SLA.md) | SLA thresholds |
| [docs/DOCKER.md](docs/DOCKER.md) | Container deployment |
| [docs/PROMETHEUS.md](docs/PROMETHEUS.md) | Prometheus integration |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Benchmark guidance |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues |
| [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) | Authorized-use policy |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | Maintainer release steps |

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
