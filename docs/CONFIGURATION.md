# Configuration

Neural Blitz NG uses YAML for defaults, targets, and monitor settings.

## Top-level sections

| Section | Purpose |
| ------- | ------- |
| `defaults` | Shared test defaults merged into per-command settings |
| `test` | Single-run test defaults |
| `server` | Echo server bind/port |
| `monitor` | HTTP monitor bind, port, interval, history |
| `targets` | Batch/monitor target list |
| `sla` | Inline SLA thresholds (or per-target `sla:` path) |

## Example

```yaml
defaults:
  count: 1000
  concurrency: 50
  timeout: 2.0
  rate: 1000

monitor:
  bind: "0.0.0.0"
  http_port: 8888
  interval: 30
  history_limit: 100

targets:
  - label: local
    host: 127.0.0.1
    port: 9999
    sla: examples/sla.yaml
```

## Validation

```bash
neural-blitz validate-config examples/neural_blitz.yaml
neural-blitz validate-sla examples/sla.yaml
```

`validate-config` applies the bundled strict JSON Schema and runtime
validation. Unknown keys are rejected. The schema covers every `test`,
`server`, and `monitor` setting, including test output/buffer/progress and
authorization fields; server packet/rate/client-state fields; and monitor
authentication, TLS, staleness, and persistence fields.

## CLI overrides

Any test flag overrides YAML values. Use `--config` to load a base file.

## Safety

Public targets require `--i-understand-authorized-target` on the CLI or `authorized_target: true` in config (use only with permission).
