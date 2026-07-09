# Quickstart

Measure UDP latency locally in five minutes.

## 1. Install

```bash
pip install -e ".[dev,pdf]"
```

## 2. Start echo server

```bash
neural-blitz server --bind 127.0.0.1 --port 9999
```

## 3. Run a test

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --count 1000 --concurrency 50
```

## 4. Export metrics

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --metrics-output metrics/latest.json
```

## 5. Monitor continuously

```bash
neural-blitz monitor --targets-file examples/neural_blitz.yaml --http-port 8888
curl http://127.0.0.1:8888/health
```

See [CONFIGURATION.md](CONFIGURATION.md) and [DOCKER.md](DOCKER.md) for deployment details.
