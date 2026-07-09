.PHONY: install dev lint format test coverage docker-build docker-up clean

install:
	python3 -m pip install -e .

dev:
	python3 -m pip install -e ".[dev,pdf]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

test:
	pytest -q

coverage:
	pytest --cov=neural_blitz --cov-report=term-missing -q

docker-build:
	docker build -t neural-blitz-ng .

docker-up:
	docker compose up --build -d

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
