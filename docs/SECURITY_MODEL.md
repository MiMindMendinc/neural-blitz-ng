# Security Model

Neural Blitz NG is a **defensive monitoring tool**, not a network attack framework.

## Design principles

1. **Local-first defaults** — targets default to `127.0.0.1`
2. **Explicit authorization** — public targets require `--i-understand-authorized-target`
3. **Bounded load** — ceilings on count, concurrency, rate, packet size, timeout
4. **No abuse primitives** — no scanning, spoofing, amplification, or credential features
5. **Auditable output** — JSON/CSV/Prometheus for operators and compliance-friendly logs

## Safety ceilings (defaults)

| Parameter | Default max/min |
| --------- | --------------- |
| `count` | 1,000,000 |
| `concurrency` | 10,000 |
| `rate` | 100,000 pps |
| `size` | 65,507 bytes |
| `timeout` | 0.01 – 60 seconds |

Override via environment variables (`NEURAL_BLITZ_MAX_COUNT`, etc.) with warnings.

## UDP echo behavior

The server validates the Neural Blitz packet header before echoing. It drops
malformed, oversized, and optionally rate-limited datagrams. Configure
`server.max_packet_size` and `server.rate_limit` when exposing it beyond a
trusted host; firewall the UDP port so only approved clients can reach it.

## Monitor API

The monitor can read an opaque bearer token from `monitor.auth_token_file`.
The secret is read once at startup and is never logged. Requests then require
`Authorization: Bearer <token>`; `/health` remains probe-friendly unless
`monitor.health_requires_auth` is true. Native TLS is available with
`monitor.tls_cert_file` and `monitor.tls_key_file`; production deployments may
terminate TLS at a trusted ingress instead.

Do not place tokens in YAML or environment variables. Mount a file readable
only by the monitor process, for example under `/run/secrets`.

## Operator responsibilities

- Obtain written permission before benchmarking third-party networks
- Rate-limit tests on shared infrastructure
- Do not expose echo servers to the public internet without intent
- Review [SECURITY.md](../SECURITY.md) for vulnerability reporting

## Exit code 5

Safety policy violations return exit code `5` (`EXIT_SAFETY_VIOLATION`).
