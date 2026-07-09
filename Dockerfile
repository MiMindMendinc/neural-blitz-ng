FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEURAL_BLITZ_NO_UVLOOP=0

WORKDIR /app

RUN groupadd --gid 10001 neuralblitz && \
    useradd --uid 10001 --gid neuralblitz --create-home --shell /usr/sbin/nologin neuralblitz

COPY pyproject.toml README.md ./
COPY neural_blitz ./neural_blitz
COPY neural_blitz_ng.py ./
COPY examples/neural_blitz.yaml ./config/neural_blitz.yaml
COPY examples/sla.yaml ./config/sla.yaml

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir .

RUN mkdir -p /app/metrics /app/reports && chown -R neuralblitz:neuralblitz /app

USER neuralblitz

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/health', timeout=3)"

CMD ["neural-blitz", "monitor", "--targets-file", "/app/config/neural_blitz.yaml", "--http-port", "8888", "--interval", "30"]
