# Configuration

Neural Blitz NG uses YAML for defaults, targets, and monitor settings.

## Operator profiles

```bash
neural-blitz init-config --list-profiles
neural-blitz init-config --profile starlink
neural-blitz init-config --profile mesh --output mesh.yaml
```

| Profile | When to use | Notes |
| ------- | ----------- | ----- |
| `local` | Loopback benches and CI | Tight SLA, higher rate |
| `starlink` | Residential LEO uplink | Gentle 50 pps, 60s interval, handover-tolerant SLA |
| `mesh` | Multi-hop backhaul | One target per hop you own, 5s timeout |
| `nonprofit` | Clinic / school / field site | 2-minute interval, telehealth-oriented SLA |

`init-config` writes the YAML and a sibling SLA file (`sla-starlink.yaml`, etc.). Defaults stay on `127.0.0.1` so first-run works; point `host` at **your** echo server, then pass `--i-understand-authorized-target` for non-private destinations.

Repo copies: `examples/starlink-residential.yaml`, `examples/mesh-multihop.yaml`, `examples/nonprofit-remote-site.yaml`.

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

Batch and monitor merge each targets file's `defaults` with its `test` section, then apply per-target keys. Profile `defaults:` (count, rate, concurrency, timeout) are honored.

## Safety

Public targets require `--i-understand-authorized-target` on the CLI or `authorized_target: true` in config (use only with permission). `--i-understand-authorized-target` on `monitor` and `batch` is applied to the in-memory config so reloads keep the authorization for that process.

## Monitor hot-reload

Monitor mode reloads the targets file when the mtime changes, and immediately on `SIGHUP`.

Reloaded without restart:

- `targets` list (add/remove/edit hops)
- `defaults` / per-target test settings from that file
- `monitor.interval`, `monitor.history_limit`, `monitor.stale_after_seconds`

Require a process restart:

- HTTP bind/port, TLS certs, auth token file

Invalid YAML or failed validation **keeps the last-good config** and records `config_reload_error` on `/health`. Removed targets are dropped from Prometheus output.

```bash
neural-blitz monitor --targets-file neural_blitz.yaml
# edit the YAML, or:
kill -HUP "$(pidof neural-blitz)"
```

`--no-reload` pins the startup file for the life of the process.
