# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 9.x     | Yes       |
| 8.x     | Best effort |

## Reporting a vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Email or contact Michigan MindMend Inc. through the repository security advisory process:

1. Go to the repository **Security** tab
2. Choose **Report a vulnerability**
3. Include reproduction steps, impact, and suggested fix if available

We aim to acknowledge reports within 5 business days.

## Security model

Neural Blitz NG is designed for **authorized** UDP latency monitoring:

- Default targets are localhost/private addresses
- Public targets require `--i-understand-authorized-target`
- Hard ceilings on count, concurrency, rate, and packet size
- No scanning, spoofing, or amplification features

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) for details.

## Safe deployment

- Run monitor mode behind a firewall when possible
- Do not expose UDP echo servers to untrusted networks without intent
- Mount configuration read-only in containers
- Run Docker images as non-root (default in provided Dockerfile)

## Dependency updates

Security-relevant dependency updates are handled through CI, CodeQL, and release tagging.
