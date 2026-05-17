# Spec #1A — Foundation & Dev Stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estabelecer fundação do repositório monorepo: estrutura de diretórios, Docker Compose para dev, PostgreSQL com schemas `znuny` e `gerti` + RLS, esqueleto do sidecar Python/FastAPI com migrations, e suite de testes integrada — pronta para todas as sub-entregas da Spec #1.

**Architecture:** Repositório monorepo organizado em `apps/sidecar` (Python/FastAPI), `apps/portal` (Vue 3 + Nuxt 3 — a popular em 1F), `services/znuny-hooks` (Perl .opm — a popular em 1B) e `infra/compose` (Docker Compose dev/prod). Um único cluster PostgreSQL com schemas separados `znuny` e `gerti`; RLS habilitado nas tabelas `gerti.*`; role `gerti_app` (RLS), `gerti_admin` (BYPASSRLS) e `znuny_owner` (dono do schema znuny). Sidecar expõe FastAPI com middleware de tenant que faz `SET LOCAL app.current_tenant`. Smoke tests em pytest com testcontainers confirmam isolamento RLS e conectividade.

**Tech Stack:** Python 3.12, uv (package manager), FastAPI 0.115+, SQLAlchemy 2.x (async), asyncpg, Alembic, Pydantic v2, pytest + pytest-asyncio + testcontainers-python, PostgreSQL 16, Redis 7, MinIO, Docker Compose v2, Traefik v3. Spec #0 §3.2 e §4.2 são a referência canônica.

---

## File Structure

Será criado neste plano:

```
gerti/
├── apps/
│   └── sidecar/
│       ├── pyproject.toml                  uv-managed project
│       ├── README.md
│       ├── .env.example
│       ├── alembic.ini
│       ├── alembic/
│       │   ├── env.py                      async-aware
│       │   ├── script.py.mako
│       │   └── versions/
│       │       └── 0001_initial_schema.py  cria znuny_instance + tenant
│       ├── src/
│       │   └── gerti_sidecar/
│       │       ├── __init__.py
│       │       ├── main.py                 FastAPI app + lifespan
│       │       ├── config.py               pydantic-settings
│       │       ├── db.py                   async engine + session
│       │       ├── middleware/
│       │       │   ├── __init__.py
│       │       │   └── tenant.py           subdomain → tenant → SET LOCAL
│       │       ├── models/
│       │       │   ├── __init__.py
│       │       │   ├── base.py             DeclarativeBase
│       │       │   ├── znuny_instance.py
│       │       │   └── tenant.py
│       │       └── routers/
│       │           ├── __init__.py
│       │           └── health.py           /v1/health
│       └── tests/
│           ├── conftest.py                 fixtures: db, client, tenant
│           ├── test_health.py
│           ├── test_db_connection.py
│           └── test_rls_isolation.py       valida que RLS impede cross-tenant
├── infra/
│   ├── compose/
│   │   ├── .env.example
│   │   ├── docker-compose.base.yml         serviços compartilhados
│   │   ├── docker-compose.dev.yml          override dev
│   │   └── postgres/init/
│   │       └── 001_schemas_and_roles.sql   cria schemas e roles
│   └── README.md
├── .editorconfig
├── .github/
│   └── workflows/
│       └── sidecar-ci.yml                  lint + tests do sidecar
└── docs/
    └── adr/
        └── 0001-monorepo-layout.md         doc da decisão de layout
```

Files referenciados (já existentes no commit `bde9278`):
- `docs/superpowers/specs/2026-05-12-gerti-servicedesk-znuny-design.md`

---

## Task 1: Inicializar estrutura do monorepo

**Files:**
- Create: `.editorconfig`
- Create: `apps/sidecar/.gitkeep`
- Create: `apps/portal/.gitkeep`
- Create: `services/znuny-hooks/.gitkeep`
- Create: `infra/compose/.gitkeep`
- Create: `docs/adr/0001-monorepo-layout.md`

- [ ] **Step 1: Criar diretórios e marcadores**

```bash
mkdir -p apps/sidecar apps/portal services/znuny-hooks infra/compose/postgres/init docs/adr
touch apps/sidecar/.gitkeep apps/portal/.gitkeep services/znuny-hooks/.gitkeep infra/compose/.gitkeep
```

- [ ] **Step 2: Escrever .editorconfig**

Arquivo `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[*.{yml,yaml,json,toml}]
indent_size = 2

[Makefile]
indent_style = tab
```

- [ ] **Step 3: Escrever ADR 0001 (monorepo layout)**

Arquivo `docs/adr/0001-monorepo-layout.md`:

```markdown
# ADR 0001 — Layout monorepo

Status: Accepted · 2026-05-12

## Contexto
A Spec #0 prevê 3 artefatos de software (sidecar Python, portal Vue 3/Nuxt 3, plugin Perl .opm) + infra
declarativa. Cada um tem seu ciclo de build/test, mas evoluem juntos e referenciam contratos
compartilhados (eventos, schemas).

## Decisão
Monorepo único em `gerti/` com:
- `apps/sidecar/` — código Python (FastAPI, workers Celery)
- `apps/portal/` — código Vue 3 + Nuxt 3 (SSR Universal)
- `services/znuny-hooks/` — pacote Perl .opm
- `infra/compose/` — Docker Compose + scripts de provisionamento
- `docs/` — specs, plans, ADRs

## Consequências
+ Mudanças que cruzam camadas (ex.: novo dynamic field) podem ir em um único PR
+ Setup local com um clone só
+ CI pode rodar matriz por camada
− Disciplina exigida: PRs grandes precisam ser revisados por área
```

- [ ] **Step 4: Commit**

```bash
git add .editorconfig apps/ services/ infra/ docs/adr/
git commit -m "chore: scaffold monorepo layout (sidecar, portal, znuny-hooks, infra)"
```

---

## Task 2: Inicializar projeto Python do sidecar com uv

**Files:**
- Create: `apps/sidecar/pyproject.toml`
- Create: `apps/sidecar/README.md`
- Create: `apps/sidecar/.python-version`
- Create: `apps/sidecar/src/gerti_sidecar/__init__.py`
- Modify: `.gitignore` (já existe; garantir cobertura de uv)

- [ ] **Step 1: Verificar uv instalado**

```bash
uv --version
```

Expected: `uv 0.4.x` ou superior. Se não tiver: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 2: Criar pyproject.toml do sidecar**

Arquivo `apps/sidecar/pyproject.toml`:

```toml
[project]
name = "gerti-sidecar"
version = "0.1.0"
description = "Gerti Service Desk Sidecar API"
readme = "README.md"
requires-python = ">=3.12,<3.13"
license = { text = "Proprietary" }
authors = [{ name = "WAS Soluções em Tecnologia" }]

dependencies = [
    "fastapi[standard]>=0.115.0,<0.116",
    "uvicorn[standard]>=0.32.0,<0.33",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
    "asyncpg>=0.30.0,<0.31",
    "alembic>=1.14.0,<1.15",
    "pydantic>=2.9.0,<2.10",
    "pydantic-settings>=2.6.0,<2.7",
    "python-multipart>=0.0.20,<0.1",
    "httpx>=0.28.0,<0.29",
    "structlog>=24.4.0,<25",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0,<9",
    "pytest-asyncio>=0.24.0,<0.25",
    "pytest-cov>=6.0.0,<7",
    "testcontainers[postgres]>=4.8.0,<5",
    "ruff>=0.8.0,<0.9",
    "mypy>=1.13.0,<1.14",
    "asgi-lifespan>=2.1.0,<3",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gerti_sidecar"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S", "RUF"]
ignore = ["S101"]  # asserts em testes são OK

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 3: Criar .python-version**

Arquivo `apps/sidecar/.python-version`:

```
3.12
```

- [ ] **Step 4: Criar README do sidecar**

Arquivo `apps/sidecar/README.md`:

```markdown
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
```

- [ ] **Step 5: Criar package init**

Arquivo `apps/sidecar/src/gerti_sidecar/__init__.py`:

```python
"""Gerti Sidecar API package."""

__version__ = "0.1.0"
```

- [ ] **Step 6: Sincronizar dependências**

```bash
cd apps/sidecar && uv sync --all-extras
```

Expected: cria `.venv/` em `apps/sidecar/` com todas dependências instaladas. Verifica:

```bash
uv run python -c "import fastapi, sqlalchemy, alembic; print('OK')"
```

Expected: `OK`.

- [ ] **Step 7: Atualizar .gitignore raiz**

Adicionar à seção Python do `.gitignore` existente (já cobre `.venv/` e `__pycache__/`).
Verificar e adicionar se faltar:

```bash
grep -q '^uv.lock$' .gitignore || echo '!uv.lock' >> .gitignore
grep -q '\.python-version' .gitignore && sed -i '/\.python-version/d' .gitignore || true
```

(uv.lock deve ser commitado para builds reproduzíveis.)

- [ ] **Step 8: Commit**

```bash
git add apps/sidecar/pyproject.toml apps/sidecar/.python-version apps/sidecar/README.md apps/sidecar/src apps/sidecar/uv.lock .gitignore
git commit -m "feat(sidecar): init uv project with FastAPI + SQLAlchemy + testcontainers"
```

---

## Task 3: Postgres init script (schemas + roles)

**Files:**
- Create: `infra/compose/postgres/init/001_schemas_and_roles.sql`

- [ ] **Step 1: Escrever script de init**

Arquivo `infra/compose/postgres/init/001_schemas_and_roles.sql`:

```sql
-- Executado pelo entrypoint oficial da imagem postgres:16 quando o cluster
-- é inicializado pela primeira vez. Idempotente para permitir re-execução
-- manual em ambiente dev.

-- Schemas ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS znuny;
CREATE SCHEMA IF NOT EXISTS gerti;

-- Extensões ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Roles -------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_app') THEN
    CREATE ROLE gerti_app NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_admin') THEN
    CREATE ROLE gerti_admin NOLOGIN BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'znuny_owner') THEN
    CREATE ROLE znuny_owner NOLOGIN;
  END IF;
END $$;

-- Permissions -------------------------------------------------------
GRANT USAGE ON SCHEMA znuny TO gerti_app;
GRANT USAGE, CREATE ON SCHEMA gerti TO gerti_app, gerti_admin;
GRANT USAGE, CREATE ON SCHEMA znuny TO znuny_owner;

-- gerti_app só lê znuny (regra de ouro do ADR-003)
ALTER DEFAULT PRIVILEGES FOR ROLE znuny_owner IN SCHEMA znuny
  GRANT SELECT ON TABLES TO gerti_app;

-- Usuários aplicacionais --------------------------------------------
-- senhas via variável passada no docker-compose; aqui só placeholders
-- (re-executar via SQL em prod com senhas reais do Vault)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_sidecar') THEN
    CREATE USER gerti_sidecar PASSWORD 'dev_change_me' IN ROLE gerti_app;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gerti_admin_user') THEN
    CREATE USER gerti_admin_user PASSWORD 'dev_change_me' IN ROLE gerti_admin;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'znuny') THEN
    CREATE USER znuny PASSWORD 'dev_change_me' IN ROLE znuny_owner;
  END IF;
END $$;

-- Verificação visual ------------------------------------------------
SELECT
  rolname,
  rolbypassrls,
  array(SELECT b.rolname FROM pg_auth_members m JOIN pg_roles b ON b.oid = m.roleid WHERE m.member = r.oid) AS roles
FROM pg_roles r
WHERE rolname LIKE 'gerti_%' OR rolname IN ('znuny', 'znuny_owner');
```

- [ ] **Step 2: Commit**

```bash
git add infra/compose/postgres/init/001_schemas_and_roles.sql
git commit -m "feat(infra): postgres init script (schemas znuny+gerti, roles, extensions)"
```

---

## Task 4: docker-compose.dev.yml com postgres + redis + minio

**Files:**
- Create: `infra/compose/.env.example`
- Create: `infra/compose/docker-compose.base.yml`
- Create: `infra/compose/docker-compose.dev.yml`
- Create: `infra/README.md`

- [ ] **Step 1: Criar .env.example**

Arquivo `infra/compose/.env.example`:

```bash
# Postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=dev_change_me
POSTGRES_DB=gerti
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=dev_change_me
MINIO_PORT_API=9000
MINIO_PORT_CONSOLE=9001

# Sidecar
SIDECAR_PORT=8001
SIDECAR_DATABASE_URL=postgresql+asyncpg://gerti_sidecar:dev_change_me@postgres:5432/gerti

# Traefik
TRAEFIK_PORT_HTTP=80
TRAEFIK_PORT_DASHBOARD=8080
```

- [ ] **Step 2: Criar docker-compose.base.yml**

Arquivo `infra/compose/docker-compose.base.yml`:

```yaml
# Compose base — serviços compartilhados entre dev/staging/prod.
# Overrides em docker-compose.<env>.yml ajustam portas, volumes e ambient.

networks:
  edge:
    name: gerti_edge
  app:
    name: gerti_app
  data:
    name: gerti_data
    internal: true

volumes:
  postgres_data:
  redis_data:
  minio_data:

services:

  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init:/docker-entrypoint-initdb.d:ro
    networks:
      - data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    networks:
      - data
      - app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  sidecar:
    build:
      context: ../../apps/sidecar
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      DATABASE_URL: ${SIDECAR_DATABASE_URL}
      ENVIRONMENT: development
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - app
      - data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 3: Criar docker-compose.dev.yml**

Arquivo `infra/compose/docker-compose.dev.yml`:

```yaml
# Override de DEV: expõe portas no host, monta source para hot-reload,
# desabilita restart agressivo. Use:
#   docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up

services:

  postgres:
    ports:
      - "${POSTGRES_PORT}:5432"

  redis:
    ports:
      - "${REDIS_PORT}:6379"

  minio:
    ports:
      - "${MINIO_PORT_API}:9000"
      - "${MINIO_PORT_CONSOLE}:9001"

  sidecar:
    build:
      target: dev
    command: uv run uvicorn gerti_sidecar.main:app --host 0.0.0.0 --port 8001 --reload
    ports:
      - "${SIDECAR_PORT}:8001"
    volumes:
      - ../../apps/sidecar/src:/app/src:ro
      - ../../apps/sidecar/alembic:/app/alembic:ro
      - ../../apps/sidecar/tests:/app/tests:ro
```

- [ ] **Step 4: Criar README de infra**

Arquivo `infra/README.md`:

```markdown
# Infra Gerti — Docker Compose

## Quickstart dev

```bash
cd infra/compose
cp .env.example .env
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up postgres redis minio -d
```

Serviços expostos:
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `localhost:9000`
- MinIO Console: `localhost:9001` (login com `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`)

## Stack completa (com sidecar)

```bash
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d
```

Sidecar disponível em `http://localhost:8001`.

## Logs

```bash
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml logs -f sidecar
```

## Reset completo

```bash
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml down -v
```

Remove volumes — perda total de dados local.
```

- [ ] **Step 5: Validar sintaxe**

```bash
cd infra/compose && cp .env.example .env && docker compose -f docker-compose.base.yml -f docker-compose.dev.yml config > /dev/null && echo "OK"
```

Expected: `OK`. Se erro, corrigir antes de seguir. (Aviso sobre `build` do sidecar é OK — Dockerfile será criado na Task 6.)

- [ ] **Step 6: Subir apenas data services e validar Postgres + init script**

```bash
cd infra/compose && docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up postgres -d
sleep 8
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec -T postgres psql -U postgres -d gerti -c "\dn"
```

Expected: lista de schemas inclui `gerti`, `public`, `znuny`.

```bash
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec -T postgres psql -U postgres -d gerti -c "SELECT rolname FROM pg_roles WHERE rolname LIKE 'gerti%' OR rolname IN ('znuny','znuny_owner') ORDER BY rolname;"
```

Expected: 5 linhas (`gerti_admin`, `gerti_admin_user`, `gerti_app`, `gerti_sidecar`, `znuny`, `znuny_owner`).

- [ ] **Step 7: Commit**

```bash
git add infra/compose/.env.example infra/compose/docker-compose.base.yml infra/compose/docker-compose.dev.yml infra/README.md
git commit -m "feat(infra): docker compose dev stack (postgres+redis+minio) com init de schemas"
```

---

## Task 5: Dockerfile do sidecar

**Files:**
- Create: `apps/sidecar/Dockerfile`
- Create: `apps/sidecar/.dockerignore`

- [ ] **Step 1: Escrever Dockerfile multi-stage**

Arquivo `apps/sidecar/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7

# ---- base ----
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /usr/local/bin/uv
WORKDIR /app

# ---- deps ----
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ---- dev ----
FROM deps AS dev
RUN uv sync --frozen --all-extras --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8001/v1/health || exit 1
CMD ["uv", "run", "uvicorn", "gerti_sidecar.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ---- prod ----
FROM deps AS prod
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-install-project
RUN groupadd -r gerti && useradd -r -g gerti gerti && chown -R gerti:gerti /app
USER gerti
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8001/v1/health || exit 1
CMD ["uv", "run", "uvicorn", "gerti_sidecar.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 2: Escrever .dockerignore**

Arquivo `apps/sidecar/.dockerignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.git/
.gitignore
.env
.env.*
tests/
README.md
Dockerfile
.dockerignore
```

- [ ] **Step 3: Build image dev**

```bash
cd apps/sidecar && docker build --target dev -t gerti-sidecar:dev .
```

Expected: build conclui sem erro. Última linha contém `naming to docker.io/library/gerti-sidecar:dev`.

- [ ] **Step 4: Commit**

```bash
git add apps/sidecar/Dockerfile apps/sidecar/.dockerignore
git commit -m "feat(sidecar): Dockerfile multi-stage (base/deps/dev/prod) com uv"
```

---

## Task 6: Settings com pydantic-settings

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/config.py`
- Create: `apps/sidecar/.env.example`
- Create: `apps/sidecar/tests/test_config.py`

- [ ] **Step 1: Escrever teste primeiro**

Arquivo `apps/sidecar/tests/test_config.py`:

```python
"""Settings devem carregar de env vars e validar tipos."""

import pytest
from pydantic import ValidationError

from gerti_sidecar.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("ENVIRONMENT", "development")
    s = Settings()
    assert s.environment == "development"
    assert str(s.database_url) == "postgresql+asyncpg://u:p@host:5432/db"
    assert s.is_dev is True


def test_settings_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("ENVIRONMENT", "banana")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = Settings()
    assert s.environment == "development"
    assert s.api_v1_prefix == "/v1"
```

- [ ] **Step 2: Rodar teste (deve falhar — módulo não existe)**

```bash
cd apps/sidecar && uv run pytest tests/test_config.py -v
```

Expected: `ImportError: cannot import name 'Settings' from 'gerti_sidecar.config'` (ou ModuleNotFoundError).

- [ ] **Step 3: Implementar Settings**

Arquivo `apps/sidecar/src/gerti_sidecar/config.py`:

```python
"""Configuração centralizada do sidecar via pydantic-settings.

Todas as variáveis vêm de env (12-factor). Em dev, .env é carregado
automaticamente; em prod, secrets vêm do Vault e são exportadas como
env vars antes do processo iniciar.
"""

from __future__ import annotations

from typing import Literal

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ambiente ---------------------------------------------------------
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/v1"

    # banco ------------------------------------------------------------
    database_url: PostgresDsn

    # logging ----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def must_be_async_dsn(cls, v: PostgresDsn) -> PostgresDsn:
        scheme = str(v).split(":", 1)[0]
        if scheme != "postgresql+asyncpg":
            raise ValueError(
                f"database_url deve usar driver asyncpg (got {scheme}); "
                "use 'postgresql+asyncpg://...'"
            )
        return v

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


def get_settings() -> Settings:
    """Instância singleton lida do ambiente. Importar via dependência do FastAPI."""
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Rodar testes — devem passar**

```bash
cd apps/sidecar && uv run pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Criar .env.example do sidecar**

Arquivo `apps/sidecar/.env.example`:

```bash
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

DATABASE_URL=postgresql+asyncpg://gerti_sidecar:dev_change_me@localhost:5432/gerti
```

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/config.py apps/sidecar/.env.example apps/sidecar/tests/test_config.py
git commit -m "feat(sidecar): pydantic-settings com validação de DSN async"
```

---

## Task 7: SQLAlchemy async engine + session

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/db.py`
- Create: `apps/sidecar/src/gerti_sidecar/models/__init__.py`
- Create: `apps/sidecar/src/gerti_sidecar/models/base.py`
- Create: `apps/sidecar/tests/conftest.py`
- Create: `apps/sidecar/tests/test_db_connection.py`

- [ ] **Step 1: Escrever modelo base**

Arquivo `apps/sidecar/src/gerti_sidecar/models/base.py`:

```python
"""Base declarativa para todos os modelos do schema gerti."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


# Naming convention para migrations consistentes
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa com schema gerti default e naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="gerti")
```

- [ ] **Step 2: Criar `__init__.py` dos modelos**

Arquivo `apps/sidecar/src/gerti_sidecar/models/__init__.py`:

```python
"""Modelos SQLAlchemy do sidecar (schema gerti)."""

from gerti_sidecar.models.base import Base

__all__ = ["Base"]
```

- [ ] **Step 3: Escrever db.py (engine async + session factory)**

Arquivo `apps/sidecar/src/gerti_sidecar/db.py`:

```python
"""Engine e session factory SQLAlchemy async para Postgres."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gerti_sidecar.config import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    """Cria engine async com configurações sensatas para o ambiente."""
    return create_async_engine(
        str(settings.database_url),
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Variáveis de módulo populadas no lifespan da app (ver main.py).
# Testes podem substituir via fixture.
engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependência FastAPI: yielda uma sessão por request."""
    if SessionLocal is None:
        raise RuntimeError("DB não inicializado — chame init_db() no lifespan")
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Helper para scripts e jobs que não tem ciclo FastAPI."""
    if SessionLocal is None:
        raise RuntimeError("DB não inicializado")
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def init_db(settings: Settings) -> None:
    """Inicializa engine e session factory globais a partir das settings."""
    global engine, SessionLocal
    engine = make_engine(settings)
    SessionLocal = make_session_factory(engine)


async def dispose_db() -> None:
    """Fecha o pool de conexões; chamar no shutdown."""
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None
```

- [ ] **Step 4: Criar conftest.py com fixture de db isolado (testcontainers)**

Arquivo `apps/sidecar/tests/conftest.py`:

```python
"""Fixtures globais de testes.

Estratégia: cada sessão de pytest sobe um Postgres real via testcontainers,
roda o init script do infra/compose, popula via Alembic, e fornece sessions
isoladas por teste (rollback ao final).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from gerti_sidecar.models.base import Base

ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = (
    ROOT.parent.parent
    / "infra"
    / "compose"
    / "postgres"
    / "init"
    / "001_schemas_and_roles.sql"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        # roda init script
        import psycopg

        sync_url = pg.get_connection_url().replace("+asyncpg", "")
        with psycopg.connect(sync_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(INIT_SQL.read_text())
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container: PostgresContainer) -> str:
    return postgres_container.get_connection_url()


@pytest.fixture
async def engine(db_url: str) -> AsyncGenerator:
    eng = create_async_engine(db_url, echo=False, future=True)
    # criar tabelas do schema gerti (no Alembic real isso vem de migrations)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
        await s.rollback()
```

- [ ] **Step 5: Adicionar psycopg como dev dep**

```bash
cd apps/sidecar && uv add --dev "psycopg[binary]>=3.2,<4"
```

Expected: `Installed psycopg-3.2.x` e atualiza `uv.lock`.

- [ ] **Step 6: Escrever teste de conectividade**

Arquivo `apps/sidecar/tests/test_db_connection.py`:

```python
"""Smoke test: consigo conectar no Postgres e ver schemas znuny+gerti."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_can_select_schemas(session: AsyncSession) -> None:
    result = await session.execute(
        text("SELECT nspname FROM pg_namespace WHERE nspname IN ('znuny', 'gerti') ORDER BY nspname")
    )
    schemas = [row[0] for row in result.all()]
    assert schemas == ["gerti", "znuny"]


@pytest.mark.asyncio
async def test_can_select_roles(session: AsyncSession) -> None:
    result = await session.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname IN ('gerti_app','gerti_admin','znuny_owner') ORDER BY rolname")
    )
    roles = [row[0] for row in result.all()]
    assert roles == ["gerti_admin", "gerti_app", "znuny_owner"]
```

- [ ] **Step 7: Rodar testes**

```bash
cd apps/sidecar && uv run pytest tests/test_db_connection.py -v
```

Expected: 2 passed. Pode levar ~10s na primeira execução (download da imagem postgres:16).

- [ ] **Step 8: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/db.py apps/sidecar/src/gerti_sidecar/models apps/sidecar/tests/conftest.py apps/sidecar/tests/test_db_connection.py apps/sidecar/pyproject.toml apps/sidecar/uv.lock
git commit -m "feat(sidecar): SQLAlchemy async engine, session factory, testcontainers fixtures"
```

---

## Task 8: Modelos znuny_instance + tenant

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/znuny_instance.py`
- Create: `apps/sidecar/src/gerti_sidecar/models/tenant.py`
- Modify: `apps/sidecar/src/gerti_sidecar/models/__init__.py`
- Create: `apps/sidecar/tests/test_models.py`

- [ ] **Step 1: Escrever teste**

Arquivo `apps/sidecar/tests/test_models.py`:

```python
"""Modelos básicos: znuny_instance e tenant."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.mark.asyncio
async def test_can_create_znuny_instance(session: AsyncSession) -> None:
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="vault:znuny/dsn",
        webservice_token_secret_ref="vault:znuny/token",
        webhook_signing_secret_ref="vault:znuny/webhook",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    assert inst.id is not None
    assert inst.status == "active"


@pytest.mark.asyncio
async def test_can_create_tenant(session: AsyncSession) -> None:
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="vault:znuny/dsn",
        webservice_token_secret_ref="vault:znuny/token",
        webhook_signing_secret_ref="vault:znuny/webhook",
        mode="pool",
    )
    session.add(inst)
    await session.flush()

    t = Tenant(
        legal_name="Acme S.A.",
        trade_name="Acme",
        document="11.222.333/0001-44",
        znuny_customer_id="acme",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    assert t.id is not None
    assert t.status == "active"


@pytest.mark.asyncio
async def test_tenant_subdomain_is_unique(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    inst = ZnunyInstance(
        name="main", base_url="http://znuny:80",
        db_dsn_secret_ref="x", webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x", mode="pool",
    )
    session.add(inst)
    await session.flush()

    t1 = Tenant(
        legal_name="A", trade_name="A", document="1",
        znuny_customer_id="a1", znuny_instance_id=inst.id, subdomain="dup",
    )
    t2 = Tenant(
        legal_name="B", trade_name="B", document="2",
        znuny_customer_id="b1", znuny_instance_id=inst.id, subdomain="dup",
    )
    session.add_all([t1, t2])
    with pytest.raises(IntegrityError):
        await session.flush()
```

- [ ] **Step 2: Rodar — deve falhar (modelos não existem)**

```bash
cd apps/sidecar && uv run pytest tests/test_models.py -v
```

Expected: `ImportError: cannot import name 'Tenant'`.

- [ ] **Step 3: Escrever ZnunyInstance**

Arquivo `apps/sidecar/src/gerti_sidecar/models/znuny_instance.py`:

```python
"""Modelo ZnunyInstance — registra cada instância Znuny gerenciada."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

InstanceMode = Literal["pool", "dedicated"]


class ZnunyInstance(Base):
    __tablename__ = "znuny_instance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    db_dsn_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    webservice_token_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    webhook_signing_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[InstanceMode] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Escrever Tenant**

Arquivo `apps/sidecar/src/gerti_sidecar/models/tenant.py`:

```python
"""Modelo Tenant — um cliente da Gerti."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class Tenant(Base):
    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint("subdomain", name="uq_tenant_subdomain"),
        UniqueConstraint("znuny_customer_id", name="uq_tenant_znuny_customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    trade_name: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[str] = mapped_column(String, nullable=False)
    znuny_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    znuny_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.znuny_instance.id"),
        nullable=False,
    )
    subdomain: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 5: Atualizar `__init__.py`**

Arquivo `apps/sidecar/src/gerti_sidecar/models/__init__.py`:

```python
"""Modelos SQLAlchemy do sidecar (schema gerti)."""

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.znuny_instance import ZnunyInstance

__all__ = ["Base", "Tenant", "ZnunyInstance"]
```

- [ ] **Step 6: Rodar — devem passar**

```bash
cd apps/sidecar && uv run pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/models apps/sidecar/tests/test_models.py
git commit -m "feat(sidecar): modelos ZnunyInstance e Tenant"
```

---

## Task 9: Alembic init + primeira migration

**Files:**
- Create: `apps/sidecar/alembic.ini`
- Create: `apps/sidecar/alembic/env.py`
- Create: `apps/sidecar/alembic/script.py.mako`
- Create: `apps/sidecar/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Inicializar alembic (gera estrutura base)**

```bash
cd apps/sidecar && uv run alembic init -t async alembic
```

Expected: cria `alembic/` e `alembic.ini`. Mantém `env.py` async-ready (template "async").

- [ ] **Step 2: Editar alembic.ini — apontar para DATABASE_URL**

Substituir a linha `sqlalchemy.url = ...` em `apps/sidecar/alembic.ini` por:

```ini
sqlalchemy.url =
```

(deixe vazio — vamos ler de env via env.py)

E adicionar/garantir:

```ini
[loggers]
keys = root,sqlalchemy,alembic

[logger_alembic]
level = INFO
handlers =
qualname = alembic
```

- [ ] **Step 3: Substituir alembic/env.py**

Arquivo `apps/sidecar/alembic/env.py`:

```python
"""Alembic env (async) — usa DATABASE_URL e o metadata do sidecar."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from gerti_sidecar.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# DATABASE_URL pode vir de env ou do alembic.ini (cmd `-x url=...`)
db_url = os.environ.get("DATABASE_URL") or context.get_x_argument(as_dictionary=True).get("url")
if not db_url:
    raise RuntimeError("DATABASE_URL não definido nem via env nem via -x url=...")
config.set_main_option("sqlalchemy.url", db_url)


def include_object(object, name, type_, reflected, compare_to) -> bool:  # noqa: A002
    """Alembic só gerencia o schema gerti; ignora o schema znuny."""
    if type_ == "table" and getattr(object, "schema", None) == "znuny":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="gerti",
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="gerti",
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Verificar conexão com Postgres dev**

```bash
cd apps/sidecar && cp .env.example .env
DATABASE_URL=postgresql+asyncpg://gerti_admin_user:dev_change_me@localhost:5432/gerti \
  uv run alembic current
```

Expected: log "Will assume non-transactional DDL". Saída final vazia (não há migrations rodadas).

- [ ] **Step 5: Gerar migration inicial autogenerate**

```bash
cd apps/sidecar && \
DATABASE_URL=postgresql+asyncpg://gerti_admin_user:dev_change_me@localhost:5432/gerti \
  uv run alembic revision --autogenerate -m "initial schema (znuny_instance, tenant)"
```

Expected: cria `alembic/versions/<hash>_initial_schema_znuny_instance_tenant_.py`.

- [ ] **Step 6: Renomear arquivo gerado para versão fixa**

```bash
cd apps/sidecar/alembic/versions
mv $(ls | grep initial_schema | head -n1) 0001_initial_schema.py
sed -i "s|^revision: str = '.*'|revision: str = '0001_initial'|" 0001_initial_schema.py
sed -i "s|^down_revision: Union\[str, None\] = None|down_revision: Union[str, None] = None|" 0001_initial_schema.py
```

(O hash original ainda funciona; renomear é apenas para nomes ordenáveis.)

- [ ] **Step 7: Auditar conteúdo do arquivo gerado**

Abrir `apps/sidecar/alembic/versions/0001_initial_schema.py` e confirmar que:
- `op.create_table('znuny_instance', ..., schema='gerti')` está presente
- `op.create_table('tenant', ..., schema='gerti')` está presente
- Há a foreign key `znuny_instance_id` em `tenant`

Se autogen tiver gerado código extra (CREATE SCHEMA, etc.), remover essas linhas — schema já existe via init script (`infra/compose/postgres/init/001_schemas_and_roles.sql`).

- [ ] **Step 8: Aplicar migration**

```bash
cd apps/sidecar && \
DATABASE_URL=postgresql+asyncpg://gerti_admin_user:dev_change_me@localhost:5432/gerti \
  uv run alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, initial schema (znuny_instance, tenant)`.

- [ ] **Step 9: Verificar tabelas criadas**

```bash
docker compose -f infra/compose/docker-compose.base.yml -f infra/compose/docker-compose.dev.yml exec -T postgres \
  psql -U postgres -d gerti -c "\dt gerti.*"
```

Expected: lista contendo `gerti.alembic_version`, `gerti.tenant`, `gerti.znuny_instance`.

- [ ] **Step 10: Commit**

```bash
git add apps/sidecar/alembic.ini apps/sidecar/alembic/
git commit -m "feat(sidecar): alembic async init + migration 0001 (znuny_instance, tenant)"
```

---

## Task 10: FastAPI app skeleton + health endpoint

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/main.py`
- Create: `apps/sidecar/src/gerti_sidecar/routers/__init__.py`
- Create: `apps/sidecar/src/gerti_sidecar/routers/health.py`
- Create: `apps/sidecar/tests/test_health.py`

- [ ] **Step 1: Escrever teste de health**

Arquivo `apps/sidecar/tests/test_health.py`:

```python
"""GET /v1/health retorna 200 com status ok e env."""

import pytest
from httpx import ASGITransport, AsyncClient

from gerti_sidecar.main import create_app


@pytest.mark.asyncio
async def test_health_returns_200(monkeypatch: pytest.MonkeyPatch, db_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    from gerti_sidecar.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert "version" in body
```

> Nota: `get_settings()` é decorado com `@lru_cache` (Task 6), então o
> primeiro acesso congela os valores de ambiente; após `monkeypatch.setenv`
> é necessário `get_settings.cache_clear()` antes de `create_app()` para que
> o novo `ENVIRONMENT`/`DATABASE_URL` seja efetivamente lido (a fixture
> autouse `_reset_settings_cache` em `conftest.py` roda antes do corpo do
> teste, i.e. antes do monkeypatch, por isso o clear explícito ainda é
> necessário aqui).

- [ ] **Step 2: Rodar — deve falhar**

```bash
cd apps/sidecar && uv run pytest tests/test_health.py -v
```

Expected: `ImportError: cannot import name 'create_app'`.

- [ ] **Step 3: Escrever router de health**

Arquivo `apps/sidecar/src/gerti_sidecar/routers/__init__.py`:

```python
"""Roteadores FastAPI do sidecar."""
```

Arquivo `apps/sidecar/src/gerti_sidecar/routers/health.py`:

```python
"""Endpoint /v1/health — liveness + ambient info."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gerti_sidecar import __version__
from gerti_sidecar.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["meta"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str


@router.get("", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=__version__,
    )
```

- [ ] **Step 4: Escrever main.py com create_app + lifespan**

Arquivo `apps/sidecar/src/gerti_sidecar/main.py`:

```python
"""Bootstrap da aplicação FastAPI do sidecar.

Padrão factory + lifespan para que testes possam construir apps isoladas.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gerti_sidecar import __version__
from gerti_sidecar.config import get_settings
from gerti_sidecar.db import dispose_db, init_db
from gerti_sidecar.routers import health


logger = logging.getLogger("gerti_sidecar")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("starting sidecar (env=%s, version=%s)", settings.environment, __version__)
    init_db(settings)
    try:
        yield
    finally:
        logger.info("stopping sidecar")
        await dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Gerti Service Desk API",
        version=__version__,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix=settings.api_v1_prefix)

    return app


# Para uvicorn rodar: `uvicorn gerti_sidecar.main:app`
app = create_app()
```

- [ ] **Step 5: Rodar testes — devem passar**

```bash
cd apps/sidecar && uv run pytest tests/test_health.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Rodar app local manualmente**

```bash
cd apps/sidecar && \
DATABASE_URL=postgresql+asyncpg://gerti_sidecar:dev_change_me@localhost:5432/gerti \
ENVIRONMENT=development \
  uv run uvicorn gerti_sidecar.main:app --port 8001 &
sleep 3
curl -s http://localhost:8001/v1/health
kill %1
```

Expected: JSON `{"status":"ok","environment":"development","version":"0.1.0"}`.

- [ ] **Step 7: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/src/gerti_sidecar/routers apps/sidecar/tests/test_health.py
git commit -m "feat(sidecar): FastAPI app factory com lifespan e endpoint /v1/health"
```

---

## Task 11: Middleware de tenant (subdomain → SET LOCAL app.current_tenant)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/middleware/__init__.py`
- Create: `apps/sidecar/src/gerti_sidecar/middleware/tenant.py`
- Modify: `apps/sidecar/src/gerti_sidecar/main.py`
- Create: `apps/sidecar/tests/test_tenant_middleware.py`

- [ ] **Step 1: Escrever teste**

Arquivo `apps/sidecar/tests/test_tenant_middleware.py`:

> `/v1/health` é meta — a resolução de tenant é exercida numa rota probe não-meta (`/v1/_probe`).

```python
"""Middleware deve resolver tenant por subdomínio e setar app.current_tenant."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.fixture
async def acme_tenant(session, monkeypatch):
    inst = ZnunyInstance(
        name="main", base_url="http://znuny:80",
        db_dsn_secret_ref="x", webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x", mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Acme", trade_name="Acme", document="00",
        znuny_customer_id="acme", znuny_instance_id=inst.id, subdomain="acme",
    )
    session.add(t)
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_request_with_subdomain_sets_tenant(
    monkeypatch: pytest.MonkeyPatch, db_url: str, engine, acme_tenant: Tenant
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    # lifespan não roda sob ASGITransport: liga SessionLocal à engine de teste
    monkeypatch.setattr(
        db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    )
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://acme.suporte.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    assert response.status_code == 200
    # tenant_id deve aparecer em header de debug
    assert response.headers.get("x-gerti-tenant") == str(acme_tenant.id)


@pytest.mark.asyncio
async def test_request_without_subdomain_has_no_tenant(
    monkeypatch: pytest.MonkeyPatch, db_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://api.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    # sem subdomínio o request segue sem tenant
    assert response.status_code == 200
    assert response.headers.get("x-gerti-tenant") is None


@pytest.mark.asyncio
async def test_request_with_unknown_subdomain_returns_404(
    monkeypatch: pytest.MonkeyPatch, db_url: str, engine
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    )
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://ghost.suporte.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "tenant_not_found"
```

- [ ] **Step 2: Rodar — deve falhar**

```bash
cd apps/sidecar && uv run pytest tests/test_tenant_middleware.py -v
```

Expected: ImportError sobre middleware (módulo não existe).

- [ ] **Step 3: Escrever middleware**

Arquivo `apps/sidecar/src/gerti_sidecar/middleware/__init__.py`:

```python
"""Middlewares FastAPI."""
```

Arquivo `apps/sidecar/src/gerti_sidecar/middleware/tenant.py`:

```python
"""Middleware que resolve tenant a partir do subdomínio do Host header.

Regras:
- Endpoints `/v1/health`, `/v1/openapi.json`, `/v1/docs`, `/v1/redoc` são meta:
  toleram ausência de tenant (não exige nem resolve).
- Hosts sem subdomínio (api.gerti.com.br, localhost) → request segue sem tenant.
- Subdomínio que mapeia para tenant existente → ativa app.current_tenant.
- Subdomínio que não mapeia → 404.

Após a Spec #1D (Auth Bridge), o claim `tenant_id` do JWT terá precedência sobre
o subdomínio; aqui ainda é resolução só por host porque o JWT vem depois.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from gerti_sidecar import db
from gerti_sidecar.models import Tenant


META_PATHS: Final[set[str]] = {
    "/v1/health",
    "/v1/openapi.json",
    "/v1/docs",
    "/v1/redoc",
}

# Hosts que nunca têm subdomínio de tenant (entry-points administrativos).
ROOT_HOSTS: Final[set[str]] = {
    "api.gerti.com.br",
    "localhost",
    "127.0.0.1",
    "testserver",  # padrão do httpx
}

SUBDOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<sub>[a-z0-9][a-z0-9-]{0,62})\.suporte\.gerti\.com\.br$"
)


def extract_subdomain(host: str) -> str | None:
    """Extrai `acme` de `acme.suporte.gerti.com.br`. Retorna None se não casa."""
    host = host.split(":", 1)[0].lower()
    if host in ROOT_HOSTS:
        return None
    m = SUBDOMAIN_RE.match(host)
    return m.group("sub") if m else None


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant via subdomínio e popula request.state.tenant."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # endpoints meta passam direto
        if request.url.path in META_PATHS:
            return await call_next(request)

        host = request.headers.get("host", "")
        subdomain = extract_subdomain(host)
        if subdomain is None:
            return await call_next(request)

        if db.SessionLocal is None:
            raise RuntimeError("DB não inicializado")

        async with db.SessionLocal() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.subdomain == subdomain, Tenant.status == "active")
            )
            tenant = result.scalar_one_or_none()
            if tenant is None:
                # BaseHTTPMiddleware não roteia HTTPException pelos exception
                # handlers do FastAPI; retornamos a resposta diretamente.
                return JSONResponse(
                    status_code=404,
                    content={"detail": {"code": "tenant_not_found", "subdomain": subdomain}},
                )

            # Disponibiliza no request.state
            request.state.tenant = tenant

            response = await call_next(request)
            response.headers["x-gerti-tenant"] = str(tenant.id)
            return response
```

- [ ] **Step 4: Adicionar middleware ao main.py**

Modificar `apps/sidecar/src/gerti_sidecar/main.py` — após `app.include_router(...)`, antes de `return app`, adicionar:

```python
    from gerti_sidecar.middleware.tenant import TenantMiddleware
    app.add_middleware(TenantMiddleware)
```

(Imports no topo do arquivo são preferíveis; movam para o topo.)

Versão final do `create_app()` (substituir bloco existente):

```python
def create_app() -> FastAPI:
    from gerti_sidecar.middleware.tenant import TenantMiddleware

    settings = get_settings()
    app = FastAPI(
        title="Gerti Service Desk API",
        version=__version__,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.add_middleware(TenantMiddleware)

    return app
```

- [ ] **Step 5: Rodar testes**

```bash
cd apps/sidecar && uv run pytest tests/test_tenant_middleware.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/middleware apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_tenant_middleware.py
git commit -m "feat(sidecar): TenantMiddleware resolve tenant por subdomínio"
```

---

## Task 12: RLS smoke test (defesa em profundidade)

**Files:**
- Create: `apps/sidecar/alembic/versions/0002_rls_baseline.py`
- Create: `apps/sidecar/tests/test_rls_isolation.py`

> Esta task introduz a primeira política RLS — em `gerti.tenant` mesmo. Outras tabelas
> recebem RLS nas suas respectivas migrations à medida que são criadas. O objetivo aqui
> é validar end-to-end que o mecanismo funciona em dev.

- [ ] **Step 1: Escrever migration 0002 (RLS em tenant)**

Arquivo `apps/sidecar/alembic/versions/0002_rls_baseline.py`:

```python
"""rls baseline: ativa RLS em tenant e dá GRANT a gerti_app.

Revision ID: 0002_rls_baseline
Revises: 0001_initial
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0002_rls_baseline"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Grants para o app role consumir as tabelas
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.tenant TO gerti_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.znuny_instance TO gerti_app")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")

    # RLS na tabela tenant (o próprio tenant só vê a si mesmo)
    op.execute("ALTER TABLE gerti.tenant ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_self_isolation ON gerti.tenant
          USING (
            current_setting('app.current_tenant', true) = ''
            OR id = current_setting('app.current_tenant', true)::uuid
          )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_self_isolation ON gerti.tenant")
    op.execute("ALTER TABLE gerti.tenant DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON gerti.tenant FROM gerti_app")
    op.execute("REVOKE ALL ON gerti.znuny_instance FROM gerti_app")
```

- [ ] **Step 2: Escrever teste de isolamento**

Arquivo `apps/sidecar/tests/test_rls_isolation.py`:

```python
"""RLS deve impedir que sessão de tenant A leia linha de tenant B."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.fixture
async def app_engine(db_url: str):
    """Engine conectada como gerti_sidecar (sujeita a RLS), não como superuser."""
    # db_url do testcontainer usa user 'test'; criamos engine apontando para gerti_sidecar
    # após migrations aplicadas pelo fixture engine padrão.
    parts = db_url.replace("postgresql+asyncpg://", "").split("@", 1)
    host_part = parts[1]
    app_url = f"postgresql+asyncpg://gerti_sidecar:dev_change_me@{host_part}"
    eng = create_async_engine(app_url, echo=False)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_read(engine, app_engine) -> None:
    # 1) Seed: 2 tenants via engine admin (sem RLS aplicado a superuser).
    factory_admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory_admin() as s:
        inst = ZnunyInstance(
            name="main", base_url="x",
            db_dsn_secret_ref="x", webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x", mode="pool",
        )
        s.add(inst)
        await s.flush()
        a = Tenant(
            legal_name="A", trade_name="A", document="1",
            znuny_customer_id="acme", znuny_instance_id=inst.id, subdomain="acme",
        )
        b = Tenant(
            legal_name="B", trade_name="B", document="2",
            znuny_customer_id="beta", znuny_instance_id=inst.id, subdomain="beta",
        )
        s.add_all([a, b])
        await s.commit()
        a_id, b_id = a.id, b.id

    # 2) Sessão com role app_role + tenant A: deve ver só A.
    factory_app = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory_app() as s:
        await s.execute(text(f"SET LOCAL app.current_tenant = '{a_id}'"))
        result = await s.execute(text("SELECT id FROM gerti.tenant"))
        ids = {row[0] for row in result.all()}
    assert ids == {a_id}

    # 3) Mesma engine + tenant B: deve ver só B.
    async with factory_app() as s:
        await s.execute(text(f"SET LOCAL app.current_tenant = '{b_id}'"))
        result = await s.execute(text("SELECT id FROM gerti.tenant"))
        ids = {row[0] for row in result.all()}
    assert ids == {b_id}
```

- [ ] **Step 3: Aplicar migration 0002 em dev**

```bash
cd apps/sidecar && \
DATABASE_URL=postgresql+asyncpg://gerti_admin_user:dev_change_me@localhost:5432/gerti \
  uv run alembic upgrade head
```

Expected: `Running upgrade 0001_initial -> 0002_rls_baseline`.

- [ ] **Step 4: Garantir que conftest aplique migrations no testcontainer**

Modificar `apps/sidecar/tests/conftest.py` — substituir a fixture `engine` por uma que roda migrations Alembic em vez de `Base.metadata.create_all`:

```python
@pytest.fixture
async def engine(db_url: str) -> AsyncGenerator:
    """Engine apontando para o testcontainer, com migrations aplicadas."""
    import os
    from alembic import command
    from alembic.config import Config

    eng = create_async_engine(db_url, echo=False, future=True)

    # roda migrations
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    os.environ["DATABASE_URL"] = db_url
    await asyncio.to_thread(command.upgrade, cfg, "head")

    yield eng

    # downgrade limpa tabelas
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await eng.dispose()
```

Substitui a versão antiga (que usava `Base.metadata.create_all`).

- [ ] **Step 5: Rodar testes**

```bash
cd apps/sidecar && uv run pytest tests/test_rls_isolation.py -v
```

Expected: 1 passed. Se falhar com permission denied, conferir GRANTs do init script (Task 3).

- [ ] **Step 6: Rodar suite completa**

```bash
cd apps/sidecar && uv run pytest -v
```

Expected: todos os testes anteriores ainda passando + os novos.

- [ ] **Step 7: Commit**

```bash
git add apps/sidecar/alembic/versions/0002_rls_baseline.py apps/sidecar/tests/conftest.py apps/sidecar/tests/test_rls_isolation.py
git commit -m "feat(sidecar): RLS baseline em gerti.tenant + smoke test de isolamento"
```

---

## Task 13: Lint, type-check e CI workflow

**Files:**
- Create: `.github/workflows/sidecar-ci.yml`
- Create: `apps/sidecar/Makefile`

- [ ] **Step 1: Rodar ruff e mypy localmente**

```bash
cd apps/sidecar && uv run ruff check . && uv run ruff format --check .
```

Expected: zero issues. Se houver, corrigir com `uv run ruff check --fix .` e `uv run ruff format .`.

```bash
cd apps/sidecar && uv run mypy src
```

Expected: `Success: no issues found`. Se houver, corrigir tipos.

- [ ] **Step 2: Escrever Makefile do sidecar**

Arquivo `apps/sidecar/Makefile`:

```makefile
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
```

- [ ] **Step 3: Escrever CI workflow**

Arquivo `.github/workflows/sidecar-ci.yml`:

```yaml
name: sidecar-ci

on:
  push:
    branches: [main]
    paths:
      - "apps/sidecar/**"
      - "infra/compose/postgres/init/**"
      - ".github/workflows/sidecar-ci.yml"
  pull_request:
    paths:
      - "apps/sidecar/**"
      - "infra/compose/postgres/init/**"
      - ".github/workflows/sidecar-ci.yml"

defaults:
  run:
    working-directory: apps/sidecar

jobs:
  lint-and-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.4.30"

      - name: Set up Python
        run: uv python install 3.12

      - name: Sync deps
        run: uv sync --all-extras --frozen

      - name: Lint
        run: |
          uv run ruff check .
          uv run ruff format --check .

      - name: Typecheck
        run: uv run mypy src

      - name: Test
        run: uv run pytest -v --cov=gerti_sidecar --cov-report=term

      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: apps/sidecar/.coverage
          if-no-files-found: ignore
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/sidecar-ci.yml apps/sidecar/Makefile
git commit -m "ci: lint + mypy + pytest workflow para sidecar"
```

---

## Task 14: Smoke test end-to-end via docker compose

**Files:**
- Create: `infra/compose/scripts/smoke-test.sh`

- [ ] **Step 1: Subir stack completa**

```bash
cd infra/compose && docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d --build
sleep 15
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml ps
```

Expected: `postgres`, `redis`, `minio`, `sidecar` todos `Up` (healthy onde aplicável).

- [ ] **Step 2: Aplicar migrations do sidecar dentro do container**

```bash
cd infra/compose && docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec sidecar uv run alembic upgrade head
```

Expected: `Running upgrade 0001_initial -> 0002_rls_baseline` (ou "already at head").

- [ ] **Step 3: Bater no /v1/health pelo host**

```bash
curl -s http://localhost:8001/v1/health
```

Expected: `{"status":"ok","environment":"development","version":"0.1.0"}`.

- [ ] **Step 4: Escrever script de smoke automatizado**

Arquivo `infra/compose/scripts/smoke-test.sh`:

```bash
#!/usr/bin/env bash
# Smoke test end-to-end do stack dev.
# Sobe stack, aplica migrations, bate em /v1/health e cleanup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

trap 'docker compose -f docker-compose.base.yml -f docker-compose.dev.yml down -v' EXIT

echo "→ Subindo stack..."
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d --build

echo "→ Aguardando postgres..."
for i in {1..30}; do
  if docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec -T postgres pg_isready -U postgres -d gerti >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "→ Aplicando migrations..."
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec -T sidecar uv run alembic upgrade head

echo "→ Aguardando sidecar..."
for i in {1..30}; do
  if curl -fsS http://localhost:8001/v1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "→ Smoke: GET /v1/health"
response="$(curl -fsS http://localhost:8001/v1/health)"
echo "  resp: $response"
echo "$response" | grep -q '"status":"ok"' || { echo "✗ status != ok"; exit 1; }
echo "$response" | grep -q '"environment":"development"' || { echo "✗ env != development"; exit 1; }

echo "→ Smoke: SQL no postgres"
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml exec -T postgres \
  psql -U postgres -d gerti -tAc "SELECT COUNT(*) FROM gerti.alembic_version" | grep -qE '^[0-9]+$' \
  || { echo "✗ alembic_version não acessível"; exit 1; }

echo "✓ smoke-test OK"
```

```bash
chmod +x infra/compose/scripts/smoke-test.sh
```

- [ ] **Step 5: Rodar smoke**

```bash
infra/compose/scripts/smoke-test.sh
```

Expected: termina com `✓ smoke-test OK`. Se falhar em algum passo, diagnosticar logs com `docker compose logs <service>`.

- [ ] **Step 6: Commit**

```bash
git add infra/compose/scripts/smoke-test.sh
git commit -m "feat(infra): smoke-test e2e (compose up + migrations + /v1/health)"
```

---

## Task 15: Atualizar README raiz com instruções de quickstart

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Substituir README.md raiz**

Substituir conteúdo de `README.md`:

```markdown
# Gerti Service Desk — plataforma own-source baseada em Znuny

Projeto de plataforma de Service Desk multi-tenant para a **Gerti** (MSP de TI, São Paulo) operar internamente e atender seus clientes finais, substituindo o **Tiflux SaaS** atualmente em `suporte.gerti.com.br`.

Preparado pela **WAS Soluções em Tecnologia**.

## Estrutura

```
.
├── apps/
│   ├── sidecar/     Python · FastAPI · SQLAlchemy · Alembic · Celery (a popular)
│   └── portal/      Vue 3 · Nuxt 3 (a popular em Spec #1F)
├── services/
│   └── znuny-hooks/ Pacote Perl .opm (a popular em Spec #1B)
├── infra/
│   └── compose/     Docker Compose dev/staging/prod + scripts
└── docs/
    ├── adr/         Architecture Decision Records
    └── superpowers/
        ├── specs/   Specs técnicas (Spec #0 cobre arquitetura geral)
        └── plans/   Planos de implementação executáveis
```

## Quickstart dev

Requisitos: Docker 24+, Docker Compose v2, Python 3.12, uv.

```bash
# 1) Subir infra
cd infra/compose
cp .env.example .env
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up postgres redis minio -d

# 2) Setup sidecar
cd ../../apps/sidecar
uv sync --all-extras
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn gerti_sidecar.main:app --reload --port 8001

# em outra aba: testar
curl http://localhost:8001/v1/health
```

Ou rodar tudo via Compose:

```bash
cd infra/compose
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d --build
infra/compose/scripts/smoke-test.sh
```

## Apresentação interativa do plano (para stakeholders)

Veja `apresentacao/` ou hospede `apresentacao-was-gerti.zip` em Netlify/Vercel.

## Stack alvo

- **Znuny LTS** (Perl + mod_perl) — core ticketing/ITSM/CMDB, inalterado
- **GertiHooks.opm** — pacote Perl mínimo (dynamic fields + event handlers)
- **Sidecar Python** — FastAPI + SQLAlchemy + Alembic + Celery + Redis
- **PostgreSQL 16** — cluster único, schemas `znuny` e `gerti` com RLS
- **Portal Cliente** — Vue 3 + Nuxt 3 (SSR Universal) + Nuxt UI v3 + Pinia + Tailwind + TypeScript
- **Deploy** — Docker Compose (uma stack por instância)

## Documentos

- [Spec #0 — arquitetura geral](docs/superpowers/specs/2026-05-12-gerti-servicedesk-znuny-design.md)
- [Roadmap de planos da Spec #1](docs/superpowers/plans/2026-05-12-spec-1-roadmap.md)
- [Plano 1A — Foundation & Dev Stack](docs/superpowers/plans/2026-05-12-spec-1a-foundation.md) (este)

## Próximos planos (a serem detalhados)

- 1B — GertiHooks.opm
- 1C — Sidecar core domain & repositories
- 1D — Auth Bridge OIDC
- 1E — Sidecar APIs públicas
- 1F — Portal Cliente SPA MVP
- 1G — Onboarding tenant + admin

## Comandos úteis

```bash
# Sidecar
cd apps/sidecar
make check       # lint + typecheck + test
make run         # uvicorn --reload
make upgrade     # alembic upgrade head

# Infra
cd infra/compose
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d
docker compose -f docker-compose.base.yml -f docker-compose.dev.yml down -v   # reset total
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: atualizar README raiz com quickstart dev e estrutura monorepo"
```

---

## Resumo final

Após executar todas as tasks, o repositório terá:

- ✅ Monorepo escaffolded (`apps/sidecar`, `apps/portal`, `services/znuny-hooks`, `infra/compose`)
- ✅ Docker Compose dev stack funcional (Postgres + Redis + MinIO + Sidecar)
- ✅ PostgreSQL com schemas `znuny` e `gerti`, roles `gerti_app`/`gerti_admin`/`znuny_owner`
- ✅ Sidecar FastAPI com lifespan, settings tipadas, engine async
- ✅ Migrations Alembic (init schema + RLS baseline)
- ✅ TenantMiddleware resolvendo subdomínio → tenant
- ✅ Suite de testes pytest com testcontainers (RLS + DB + health + middleware)
- ✅ CI GitHub Actions (lint + mypy + pytest)
- ✅ Smoke test e2e via shell script
- ✅ README quickstart

**Definition of done deste plano**: `infra/compose/scripts/smoke-test.sh` passa, `make check` no sidecar verde, `git log` com ~15 commits estruturados, fundação pronta para Plano 1B (GertiHooks.opm) começar.
