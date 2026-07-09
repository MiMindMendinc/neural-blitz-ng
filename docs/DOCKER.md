# Docker Deployment

## Build

```bash
docker build -t neural-blitz-ng .
```

## Compose (monitor mode)

```bash
docker compose up --build
```

Endpoints:

- http://127.0.0.1:8888/health
- http://127.0.0.1:8888/metrics
- http://127.0.0.1:8888/metrics/prometheus

## Volumes

| Mount | Purpose |
| ----- | ------- |
| `./examples/neural_blitz.yaml` | Read-only config |
| `./metrics` | Exported metrics |
| `./reports` | PDF reports |

## Security notes

- Container runs as non-root user `neuralblitz`
- Healthcheck probes `/health`
- Default targets are localhost — update config deliberately for real deployments
