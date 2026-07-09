# SLA Checks

Define reliability thresholds in YAML and evaluate after each test.

## Supported thresholds

```yaml
min_success_rate: 99.9
max_loss_rate: 1.0
max_mean_us: 500.0
max_p95_us: 1500.0
max_p99_us: 2500.0
max_p999_us: 5000.0
max_co_p99_us: 3000.0
max_jitter_us: 500.0
min_pps: 100.0
```

## Usage

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --sla examples/sla.yaml --fail-on-sla
```

Exit code `2` indicates SLA failure when `--fail-on-sla` is set.

## Validation

```bash
neural-blitz validate-sla examples/sla.yaml
```

Failures list actual vs threshold for each violated check.
