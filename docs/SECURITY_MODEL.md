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

The server echoes received payloads unchanged. It does not reflect traffic to third parties or amplify requests.

## Operator responsibilities

- Obtain written permission before benchmarking third-party networks
- Rate-limit tests on shared infrastructure
- Do not expose echo servers to the public internet without intent
- Review [SECURITY.md](../SECURITY.md) for vulnerability reporting

## Exit code 5

Safety policy violations return exit code `5` (`EXIT_SAFETY_VIOLATION`).
