# Changelog

All notable changes to Neural Blitz NG are documented here.

## [9.0.0] - 2026-07-09

### Added
- Proper `neural_blitz` Python package with modular architecture
- `safety.py` with rate/count/concurrency ceilings and authorized-target gate
- `validate-config` and `validate-sla` CLI commands
- `version` subcommand with JSON output
- Comparison regression thresholds (`--max-p95-regression`, `--fail-on-regression`)
- Expanded metrics: loss_rate, duplicate/malformed/out-of-order counters, host/port/timestamp
- Prometheus metrics renamed to `neural_blitz_*` with label/host/port labels
- Versioned UDP packet header (25 bytes)
- Comprehensive test suite with pytest markers and 85%+ coverage target
- GitHub Actions: ruff, mypy, coverage, CodeQL, release workflow
- Documentation tree under `docs/`
- Examples for YAML, SLA, Prometheus, and Grafana
- Makefile, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md
- Non-root Docker image with healthcheck

### Changed
- Default server bind is `127.0.0.1` (was `0.0.0.0`)
- `reportlab` is optional (`pip install neural-blitz-ng[pdf]`)
- Python 3.10+ support (was 3.11+)
- README rewritten for production open-source presentation

### Preserved
- All core commands: `server`, `test`, `batch`, `monitor`, `compare`, `init-config`
- `neural_blitz_ng.py` compatibility wrapper
- MIT license

## [8.0.0] - prior release

- Single-file CLI with Rich output, YAML config, SLA, PDF reports, monitor mode
