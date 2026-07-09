# Neural Blitz NG — Production Upgrade Plan

## Current State (v8.0.0 audit)

### What exists
- Single-file application (`neural_blitz_ng.py`, ~1,650 lines) with working UDP echo, test, batch, monitor, compare, init-config
- Basic CI (Python 3.11/3.12, pytest only)
- Minimal Dockerfile and docker-compose
- Example `neural_blitz.yaml` and `sla.yaml`
- 8 unit tests in `tests/test_core.py`
- MIT license, basic README

### Problems found
| Area | Issue |
|------|-------|
| Architecture | Monolithic script; hard to test, extend, or review |
| Safety | No rate/count/concurrency ceilings; no authorized-target gate |
| Metrics | Missing duplicate/malformed/loss_rate fields; no host/port/timestamp/version |
| Prometheus | Non-standard metric names (`nblitz_*`); limited labels |
| Packet | No version byte in header |
| CLI | Missing `validate-config`, `validate-sla`, `version` subcommands |
| Compare | No regression thresholds or exit code 4 on failure |
| Exit codes | Missing 5 (safety), 6 (dependency), 130 (interrupt) |
| Tests | ~8 tests; no integration tests; no coverage gate |
| Docs | No `docs/` tree; no SECURITY/CONTRIBUTING/CODE_OF_CONDUCT |
| CI | No ruff, mypy, coverage, CodeQL, release workflow |
| Docker | Runs as root; no healthcheck; no non-root user |
| pyproject | Python 3.11+ only; reportlab required (should be optional) |

## Architecture Target

```
neural_blitz/
├── __init__.py          # version, public API
├── __main__.py          # python -m neural_blitz
├── cli.py               # argparse subcommands
├── config.py            # YAML load/merge/validate
├── constants.py         # version, exit codes, limits
├── errors.py            # typed exceptions
├── safety.py            # limits + authorized-target checks
├── latency.py           # packet + LatencyRecorder
├── metrics.py           # LatencyStats, I/O
├── udp_client.py        # client protocol, run_test
├── udp_server.py        # echo server
├── monitor.py           # HTTP monitor loop
├── prometheus.py        # text exposition
├── sla.py               # SLA load/evaluate
├── compare.py           # baseline comparison
├── report_pdf.py        # optional PDF
└── logging_setup.py     # Rich/plain logging
```

Compatibility wrapper: `neural_blitz_ng.py` → imports `neural_blitz.cli.main`

## Security Hardening List

- [x] Max count ≤ 1_000_000 (configurable via env/flag with warning)
- [x] Max concurrency ≤ 10_000
- [x] Max rate ≤ 100_000 pps
- [x] Max packet size ≤ 65_507
- [x] Timeout 0.01–60 s
- [x] Block non-localhost targets without `--i-understand-authorized-target`
- [x] Responsible-use banner on test/batch/monitor
- [x] No scanning, spoofing, amplification, or raw crafting
- [x] SECURITY.md with disclosure process

## Test Plan

| Module | Target coverage | Key cases |
|--------|----------------|-----------|
| config | 90%+ | merge, bad YAML, bad ports |
| metrics | 90%+ | JSON/CSV round-trip, fields |
| latency | 85%+ | packet build/parse, percentiles, CO |
| sla | 90%+ | pass/fail messages |
| compare | 90%+ | regression thresholds |
| prometheus | 85%+ | metric names/labels |
| cli | 85%+ | help, invalid config |
| integration | — | local UDP echo happy path |

Markers: `unit`, `integration`, `slow`

## Documentation Plan

- README rewrite with badges, safety notice, quick start
- `docs/QUICKSTART.md`, `CONFIGURATION.md`, `METRICS.md`, `SLA.md`
- `docs/DOCKER.md`, `PROMETHEUS.md`, `TROUBLESHOOTING.md`, `SECURITY_MODEL.md`, `PERFORMANCE.md`
- `examples/` with commented YAML + prometheus/grafana samples
- CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY

## Release Checklist

1. Bump version in `neural_blitz/constants.py` and `pyproject.toml`
2. Update CHANGELOG.md
3. `make lint && make test && make coverage`
4. `docker build` + `docker compose config`
5. Tag `vX.Y.Z` → release workflow builds wheel/sdist
6. Publish to PyPI when token configured

## Implementation Status

See `UPGRADE_REPORT.md` for final deliverables after upgrade completes.
