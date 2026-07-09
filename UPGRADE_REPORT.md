# Neural Blitz NG — Upgrade Report (v9.0.0)

## Summary

Neural Blitz NG was refactored from a ~1,650-line monolithic script into a production-grade Python package while preserving all core commands and adding safety hardening, expanded metrics, documentation, CI, and comprehensive tests.

**Recommended release:** `v9.0.0`

## What changed

### Architecture
- New `neural_blitz/` package with 16 focused modules
- `neural_blitz_ng.py` retained as a thin compatibility wrapper
- Versioned UDP packet header (`PACKET_VERSION=1`, 25-byte header)
- Extracted `build_monitor_app()` for testable HTTP endpoints

### Safety
- `safety.py` with ceilings and `--i-understand-authorized-target` gate
- Default server bind changed to `127.0.0.1`
- Exit code `5` for safety violations, `6` for missing dependencies, `130` for interrupts

### Metrics & monitoring
- Expanded `LatencyStats` (loss_rate, duplicate/malformed/out-of-order, host/port/timestamp/version)
- Prometheus metrics renamed to `neural_blitz_*`
- Monitor history bounded by `history_limit`
- Atomic JSON/CSV writes

### CLI
- Added `validate-config`, `validate-sla`, `version` subcommands
- Compare regression thresholds with exit code `4`
- `--json` output on several commands
- `init-config` preserved

### Tooling & docs
- Makefile, expanded CI (Python 3.10–3.13, ruff, mypy, coverage)
- CodeQL and release workflows
- Full `docs/` tree, `examples/`, GitHub templates
- SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, CHANGELOG.md

## Files added

```
neural_blitz/               # 16 modules
tests/                      # 18 test modules
docs/                       # 11 documentation files
examples/                   # YAML, Prometheus, Grafana samples
.github/workflows/codeql.yml
.github/workflows/release.yml
.github/ISSUE_TEMPLATE/
.github/pull_request_template.md
Makefile
PLAN.md
UPGRADE_REPORT.md
.editorconfig
.dockerignore
```

## Files modified

- `neural_blitz_ng.py` — compatibility wrapper
- `pyproject.toml` — package metadata, dev tooling
- `README.md` — full rewrite
- `Dockerfile`, `docker-compose.yml`
- `.github/workflows/ci.yml`
- `neural_blitz.yaml`, `sla.yaml`
- `.gitignore`

## Commands run

```bash
python3 -m pip install -e ".[dev,pdf]"
ruff format .
ruff check .
mypy neural_blitz
pytest --cov=neural_blitz --cov-report=term-missing -q
python3 -m neural_blitz --help
neural-blitz --help
docker compose config
```

## Tests passed

- **99 tests** passed (unit + integration)
- **85.83%** overall coverage (target ≥85%)
- Key modules: config 83%, metrics 91%, sla 88%, compare 88%, prometheus 100%, latency 94%

## Breaking changes

| Change | Migration |
|--------|-----------|
| Packet header 24→25 bytes | Rebuild server + client together (same version) |
| Prometheus metric names `nblitz_*` → `neural_blitz_*` | Update scrape dashboards |
| Default server bind `0.0.0.0` → `127.0.0.1` | Pass `--bind 0.0.0.0` if needed |
| `reportlab` optional | `pip install 'neural-blitz-ng[pdf]'` |
| Public targets blocked by default | `--i-understand-authorized-target` when authorized |

**Backwards compatible:** All original subcommands (`server`, `test`, `batch`, `monitor`, `compare`, `init-config`) and `neural_blitz_ng.py` entry point.

## Remaining TODOs

1. Monitor config hot-reload (documented restart requirement for now)
2. Helm chart for Kubernetes deployments
3. Per-module 90%+ coverage for `cli.py` and `udp_server.py` (currently 84%/78%)
4. PyPI publish when `PYPI_API_TOKEN` is configured in GitHub secrets

## Tagline

*Measure the link before the outage writes the story.*

— Michigan MindMend Inc. / Neural Blitz NG
