.PHONY: install lint fmt typecheck test test-cov run upgrade down

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=gerti_sidecar --cov-report=term-missing

run:
	uv run uvicorn gerti_sidecar.main:app --reload --port 8001

upgrade:
	uv run alembic upgrade head

down:
	uv run alembic downgrade -1

check: lint typecheck test
