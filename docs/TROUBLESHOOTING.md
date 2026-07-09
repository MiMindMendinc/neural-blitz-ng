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

Monitor needs at least one completed cycle. Increase `start_period` or ensure targets are reachable.

## DNS errors

Verify host resolves: `getent hosts your-host`

## Windows notes

Signal handling may differ; use Ctrl+C to stop server/monitor.
