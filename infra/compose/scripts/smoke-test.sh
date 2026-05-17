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
