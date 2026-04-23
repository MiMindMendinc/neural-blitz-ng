# Getting Started

## 1. Install Dependencies

From the repo folder, install the runtime packages:

```powershell
python -m pip install aiohttp pyyaml reportlab rich
```

## 2. Start a Test Server

Open one terminal and run:

```powershell
python neural_blitz_ng.py server --bind 127.0.0.1 --port 9999
```

## 3. Run Your First Test

Open a second terminal and run:

```powershell
python neural_blitz_ng.py test --host 127.0.0.1 --port 9999 --metrics-output metrics\latest.json --pdf-report reports\latest.pdf
```

This produces:

- terminal summary output
- a JSON metrics file
- a PDF report

## 4. Run Batch Mode

Use the sample targets file:

```powershell
python neural_blitz_ng.py batch --targets-file neural_blitz.yaml --output batch_results.json
```

## 5. Run Monitor Mode

```powershell
python neural_blitz_ng.py monitor --targets-file neural_blitz.yaml --http-port 8888 --interval 30
```

Available endpoints:

- `/health`
- `/metrics`
- `/metrics/prometheus`

## 6. Run with Docker

```powershell
docker compose up --build
```

## 7. First Production Checklist

- replace sample targets in `neural_blitz.yaml`
- adjust SLA thresholds in `sla.yaml`
- run one benchmark and save the PDF for sales/demo use
- confirm monitor mode metrics are reachable from your environment
- keep one known-good benchmark as your baseline comparison
