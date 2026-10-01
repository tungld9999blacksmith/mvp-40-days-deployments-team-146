.PHONY: run test lint format typecheck check clean uv-sync uv-run uv-test mock-run

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

# ---- uv workspace ----
uv-sync:
	uv sync --all-packages

uv-run:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

uv-test:
	uv run pytest tests/ -v

mock-run:
	uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --host 0.0.0.0 --port 8100

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
