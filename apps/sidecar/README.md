# Gerti Sidecar API

API FastAPI que carrega a lógica de negócio do produto: contratos, ciclos, glosa,
dashboards, branding, Auth Bridge OIDC, webhooks IN/OUT. Comunica-se com o Znuny
via Generic Interface (escrita) e leitura direta do schema `znuny` (read-only).

## Setup local

```bash
cd apps/sidecar
uv sync --all-extras
uv run uvicorn gerti_sidecar.main:app --reload --port 8001
```

## Testes

```bash
uv run pytest
uv run pytest --cov=gerti_sidecar
```

## Migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "descrição"
```
