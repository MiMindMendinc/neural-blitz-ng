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
| `./examples/docker-neural_blitz.yaml` | Read-only compose config |
| `./metrics` | Exported metrics |
| `./reports` | PDF reports |

## Security notes

- Container runs as non-root user `neuralblitz`
- Healthcheck probes `/health`
- The compose example targets its `echo-server` service and sets
  `authorized_target: true`; retain this only for targets you own or are
  explicitly authorized to measure.
- Default targets are localhost — update config deliberately for real deployments
