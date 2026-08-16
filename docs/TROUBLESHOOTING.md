# Troubleshooting

## Connection refused

- Ensure echo server is running: `neural-blitz server --bind 127.0.0.1 --port 9999`
- Verify firewall allows UDP to the target port

## Low success rate

- Increase `--timeout`
- Reduce `--concurrency` or `--rate`
- Check socket buffer sizes (`--socket-rcvbuf`, `--socket-sndbuf`)

## Safety violation on public host

```
Target host 'example.com' is not localhost/private
```

Add `--i-understand-authorized-target` only when you have permission.

## PDF generation fails

```bash
pip install 'neural-blitz-ng[pdf]'
```

## Monitor healthcheck fails in Docker

Monitor needs at least one completed cycle. Increase `start_period` or ensure targets are reachable. `/live` and `/ready` are the process probes; `/health` is downstream target health.

## Config reload rejected

`/health` includes `config_reload_error` when the targets file failed validation. The process keeps the last-good targets. Run:

```bash
neural-blitz validate-config neural_blitz.yaml
```

Bind, TLS, and auth token changes still require a monitor restart. Use `--no-reload` only when you want the startup file pinned.

## DNS errors

Verify host resolves: `getent hosts your-host`

## Windows notes

Signal handling may differ; use Ctrl+C to stop server/monitor.
