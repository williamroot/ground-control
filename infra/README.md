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
