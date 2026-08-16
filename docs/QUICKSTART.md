# Quickstart

Measure UDP latency locally in five minutes.

## 1. Install

```bash
pip install -e ".[dev,pdf]"
neural-blitz init-config --list-profiles
neural-blitz init-config --profile local
```

Starlink dish, mesh backhaul, or a remote clinic site? Use `--profile starlink`, `--profile mesh`, or `--profile nonprofit`. Each writes a YAML config plus a matching SLA file. Replace `host` with your echo server before leaving localhost.

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
neural-blitz monitor --targets-file neural_blitz.yaml --http-port 8888
curl http://127.0.0.1:8888/health
```

Edit the targets file while monitor is running; it reloads on the next cycle or on `SIGHUP`. Invalid YAML is rejected and the last-good config keeps running.

See [CONFIGURATION.md](CONFIGURATION.md) and [DOCKER.md](DOCKER.md) for deployment details.

