FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README_neural_blitz_ng.md neural_blitz_ng.py ./
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir .

COPY neural_blitz.yaml ./config/neural_blitz.yaml
COPY sla.yaml ./config/sla.yaml

EXPOSE 8888

CMD ["python", "/app/neural_blitz_ng.py", "monitor", "--targets-file", "/app/config/neural_blitz.yaml", "--http-port", "8888", "--interval", "30"]
