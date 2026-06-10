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
        # Libs nativas do WeasyPrint (#1P): HTML→PDF branded de faturas.
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libcairo2 libcairo-gobject2 libffi8 \
        fonts-dejavu fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /usr/local/bin/uv
WORKDIR /app

# ---- deps ----
FROM base AS deps
COPY pyproject.toml uv.lock README.md ./
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
# Instala o PRÓPRIO projeto no venv no BUILD (rede disponível). Sem
# isto, `uv run` em runtime tentava buildar `gerti-sidecar` e resolver
# `hatchling` no pypi — mas a rede `data` é internal:true (sem internet)
# → "Could not connect, are you offline?". `--no-install-project` fica
# só no estágio `deps` (cache de camada das dependências).
RUN uv sync --frozen
# O usuário não-root `gerti` é system-user sem home → `uv run` falhava
# com "failed to create directory /home/gerti/.cache/uv: Permission
# denied". HOME e cache dentro de /app (já chowned p/ gerti); uv não
# baixa Python (usa o python3.12 da imagem), não mexe no lockfile e
# NÃO re-sincroniza em runtime (UV_NO_SYNC — rede internal, offline).
ENV HOME=/app \
    UV_CACHE_DIR=/app/.uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_FROZEN=1 \
    UV_NO_SYNC=1
RUN groupadd -r gerti && useradd -r -g gerti gerti \
    && mkdir -p /app/.uv-cache \
    && chown -R gerti:gerti /app
USER gerti
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8001/v1/health || exit 1
CMD ["uv", "run", "uvicorn", "gerti_sidecar.main:app", "--host", "0.0.0.0", "--port", "8001"]
