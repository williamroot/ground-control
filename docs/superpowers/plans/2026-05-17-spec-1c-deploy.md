# Sidecar Deploy Plan — single-cluster Postgres on the live Znuny VPS

> Sibling of `2026-05-17-spec-1c-contract-domain.md`. Execute ONLY after #1C
> is green locally (`ruff + ruff format + mypy + pytest` all pass, RLS proven
> under the unprivileged role). This plan adds the `sidecar` service to the
> production `ground-control` compose **without breaking the live Znuny
> stack, the Móveis Aurora demo, or the landing**.

## Audited deploy ground truth

- **VPS:** `100.99.49.110` (`ssh ubuntu@100.99.49.110`), repo `ground-control` cloned there, deployed via root `docker-compose.yml` + `docker-compose.override.yml`, env from `.env` + `.env.prod` (gitignored token). `Makefile` uses `DC := docker compose --env-file .env --env-file .env.prod` (D10/D52).
- **Prod Postgres:** service `postgres`, image `postgres:18`, volume `postgres-data:/var/lib/postgresql`, network `data` (`internal: true`), DB `znuny`, user `${POSTGRES_USER}` (superuser-equivalent, owns the cluster). Init scripts: `./postgres/init:/docker-entrypoint-initdb.d:ro` — **only run on first cluster init; the prod cluster is already initialized, so adding files there does NOT re-run them.**
- **Existing init in repo:** `infra/compose/postgres/init/001_schemas_and_roles.sql` (dev/test only, mounted by `infra/compose`, NOT by the root prod compose). Prod's `./postgres/init` is the Znuny one.
- **Cloudflared:** token-mode, single tunnel `znuny-dev` (hostname `znuny-dev.was.dev.br` → `znuny-web:80`), token in `.env.prod`. Landing uses a separate tunnel `ground-control` (`groundcontrol.was.dev.br`).
- **Networks:** `edge` (cloudflared↔web), `app`, `data` (`internal: true`). The sidecar needs `data` (to reach `postgres`) and `edge` (to be reachable by cloudflared).
- **Sidecar Dockerfile:** `apps/sidecar/Dockerfile`, target `prod`, non-root user, listens `:8001`, `HEALTHCHECK` on `/v1/health`, `CMD uvicorn gerti_sidecar.main:app`. **It does NOT run `alembic upgrade` on start** — the compose entrypoint must.

## Decision (rationale, 1 paragraph)

**Spec #0 mandates one Postgres cluster, two schemas (`znuny` immutable + `gerti`).** The prod cluster already exists and is healthy; its init scripts will not re-run. Standing up a second managed Postgres would violate Spec #0, double the backup/ops surface, and prevent the future `gerti → znuny` read-only views. **Definitive approach:** keep the single existing `postgres:18`; introduce schema `gerti` + roles + RLS into the *running* cluster via a **dedicated idempotent migration job** (`gerti-db-init`, a one-shot compose service running a hand-audited SQL against the live DB as the cluster superuser), then run Alembic as `gerti_admin_user`. The Znuny schema (`public`) is never touched. The sidecar runs as the unprivileged `gerti_sidecar` (RLS-subject). Exposure via a **new public hostname on the existing `znuny-dev` tunnel's account** — cleanest is a second ingress on a new tunnel-less hostname is not possible in token-mode with one connector, so we add `api-dev.was.dev.br` as a **second public hostname on the same `znuny-dev` tunnel** (token-mode tunnels support multiple public hostnames; ingress is configured in the Cloudflare Zero Trust dashboard / API, not in the connector).

---

## Task D1: Idempotent `gerti` schema + roles into the live prod cluster

**Files:**
- Create: `postgres/gerti-init/001_gerti_schema_roles.sql` (prod-grade, idempotent, parameterized passwords via psql vars)
- Modify: root `docker-compose.yml` (add `gerti-db-init` one-shot service)

- [ ] **Step 1: Author the idempotent SQL** (`postgres/gerti-init/001_gerti_schema_roles.sql`). It MUST be safe to run repeatedly against a cluster that already has the Znuny `public` schema and live data. It MUST NOT touch `public`/`znuny` Znuny objects. Mirror `infra/compose/postgres/init/001_schemas_and_roles.sql` but: (a) take `gerti_sidecar`/`gerti_admin_user` passwords from psql variables `:'sidecar_pw'` / `:'admin_pw'` (no hardcoded `dev_change_me` in prod); (b) `ALTER ROLE ... PASSWORD` if the role already exists so a rotated secret is applied; (c) keep `CREATE SCHEMA IF NOT EXISTS gerti`, `CREATE EXTENSION IF NOT EXISTS pgcrypto/btree_gin`, the `DO $$ ... IF NOT EXISTS pg_roles ... CREATE ROLE`/`CREATE USER` blocks, the GRANTs, and the `ALTER DEFAULT PRIVILEGES FOR ROLE znuny_owner IN SCHEMA znuny GRANT SELECT ... TO gerti_app`. Final `SELECT` verification block. **No `DROP`, no `CREATE SCHEMA znuny` if Znuny owns `public` (Znuny uses `public`, not `znuny` — keep the `znuny` schema creation `IF NOT EXISTS` for the future read views; harmless empty schema).**

- [ ] **Step 2: Add `gerti-db-init` one-shot service** to root `docker-compose.yml` (profile `gerti`, so it never runs on a plain `make up` of the Znuny stack unless the profile is enabled):

```yaml
  gerti-db-init:
    profiles: ["gerti"]
    image: ${POSTGRES_IMAGE:-postgres:18}
    restart: "no"
    depends_on:
      postgres: { condition: service_healthy }
    networks: [data]
    environment:
      PGHOST: ${POSTGRES_HOST:-postgres}
      PGPORT: ${POSTGRES_PORT:-5432}
      PGDATABASE: ${POSTGRES_DB:-znuny}
      PGUSER: ${POSTGRES_USER:-znuny}
      PGPASSWORD: ${POSTGRES_PASSWORD:-znuny}
    volumes:
      - ./postgres/gerti-init:/gerti-init:ro
    entrypoint: ["bash","-c"]
    command:
      - >
        psql -v ON_ERROR_STOP=1
        -v sidecar_pw="'${GERTI_SIDECAR_DB_PASSWORD:?set in .env.prod}'"
        -v admin_pw="'${GERTI_ADMIN_DB_PASSWORD:?set in .env.prod}'"
        -f /gerti-init/001_gerti_schema_roles.sql
```

- [ ] **Step 3: Run it against prod (manual, gated):**
```bash
ssh ubuntu@100.99.49.110
cd ground-control && git pull
# add to .env.prod (gitignored): GERTI_SIDECAR_DB_PASSWORD=..., GERTI_ADMIN_DB_PASSWORD=...
docker compose --env-file .env --env-file .env.prod --profile gerti run --rm gerti-db-init
# expect the verification SELECT to list gerti_app/gerti_admin/gerti_sidecar/gerti_admin_user
```
Idempotent: re-running only re-asserts roles/grants and re-applies passwords. **Verify Znuny untouched:** `curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login` still 200.

## Task D2: `sidecar` + `sidecar-migrate` services in prod compose

**Files:** Modify root `docker-compose.yml`.

- [ ] **Step 1: `sidecar-migrate` one-shot** (profile `gerti`) — runs Alembic as `gerti_admin_user` (BYPASSRLS, owns DDL), then exits:

```yaml
  sidecar-migrate:
    profiles: ["gerti"]
    build: { context: ./apps/sidecar, target: prod }
    image: ground-control/sidecar:${GERTI_SIDECAR_VERSION:-dev}
    restart: "no"
    depends_on:
      postgres: { condition: service_healthy }
    networks: [data]
    environment:
      DATABASE_URL: postgresql+asyncpg://gerti_admin_user:${GERTI_ADMIN_DB_PASSWORD}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-znuny}
    command: ["uv","run","alembic","upgrade","head"]
```

- [ ] **Step 2: `sidecar` long-running service** (profile `gerti`) — runs as `gerti_sidecar` (RLS-subject), waits for migrate to finish:

```yaml
  sidecar:
    profiles: ["gerti"]
    build: { context: ./apps/sidecar, target: prod }
    image: ground-control/sidecar:${GERTI_SIDECAR_VERSION:-dev}
    restart: unless-stopped
    depends_on:
      postgres:        { condition: service_healthy }
      sidecar-migrate:  { condition: service_completed_successfully }
    networks: [data, edge]
    environment:
      ENVIRONMENT: production
      DATABASE_URL: postgresql+asyncpg://gerti_sidecar:${GERTI_SIDECAR_DB_PASSWORD}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-znuny}
      LOG_LEVEL: INFO
    healthcheck:
      test: ["CMD-SHELL","curl -fsS http://127.0.0.1:8001/v1/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 20s
```

> **Why `condition: service_completed_successfully` on `sidecar-migrate`:** guarantees the schema is at `head` (incl. all RLS) before the app accepts traffic. The app role `gerti_sidecar` cannot run DDL (correct least-privilege).

- [ ] **Step 3: Deploy:**
```bash
ssh ubuntu@100.99.49.110
cd ground-control && git pull
docker compose --env-file .env --env-file .env.prod --profile gerti build sidecar
docker compose --env-file .env --env-file .env.prod --profile gerti up -d sidecar
docker compose --env-file .env --env-file .env.prod --profile gerti ps
# sidecar healthy; sidecar-migrate exited 0
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select count(*) from gerti.contract;"   # 0 rows, table exists → migrations applied
```

## Task D3: Cloudflare ingress for `api-dev.was.dev.br`

The connector token does not change. A token-mode tunnel can serve multiple public hostnames; ingress is configured server-side (dashboard or API), not in `cloudflared`'s args.

- [ ] **Step 1: API ingress** (token with `Cloudflare Tunnel:Edit` + `Zone:DNS:Edit`):
  - Add public hostname `api-dev.was.dev.br` → service `http://sidecar:8001` to tunnel `znuny-dev` via `PUT /accounts/{acct}/cfd_tunnel/{tunnel_id}/configurations` (append an ingress rule **before** the catch-all 404; keep the existing `znuny-dev.was.dev.br → http://znuny-web:80` rule first).
- [ ] **Step 2: DNS** — `CNAME api-dev → <tunnel_id>.cfargotunnel.com`, **proxied**, via `POST /zones/{zone}/dns_records`. If the token lacks `Zone:DNS:Edit`, create manually in the dashboard (flagged — not a code blocker).
- [ ] **Step 3: cloudflared must reach `sidecar`** — the tunnel ingress points at `http://sidecar:8001`; `cloudflared` is on `edge`, `sidecar` is on `edge`+`data`. No connector restart needed (config is pulled). Verify: `curl -fsS https://api-dev.was.dev.br/v1/health` → `200`.

## Task D4: Rollback + verification checklist (zero tolerance)

- [ ] **Rollback (sidecar only, Znuny untouched):**
  `docker compose --env-file .env --env-file .env.prod --profile gerti stop sidecar` then `git checkout <prev-sha> -- apps/sidecar docker-compose.yml && docker compose ... --profile gerti up -d sidecar`. Schema rollback (only if a bad migration shipped): `docker compose ... run --rm sidecar-migrate uv run alembic downgrade -1`. **Never** `make reset` (destroys the shared Znuny DB).
- [ ] **Verification (all MUST pass):**
  - `docker compose ps`: postgres/redis/opensearch/znuny-web/znuny-daemon/**sidecar** `healthy`; sidecar-migrate exited `0`.
  - `curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login` → 200 (Znuny + Aurora demo intact).
  - `curl -fsS https://groundcontrol.was.dev.br` → 200 (landing intact).
  - `curl -fsS https://api-dev.was.dev.br/v1/health` → 200 JSON.
  - **RLS real on prod:** `docker compose exec -T postgres psql -U gerti_sidecar -d "$POSTGRES_DB" -c "select * from gerti.tenant;"` with no `app.current_tenant` set → **0 rows** (fail-closed); and `relrowsecurity AND relforcerowsecurity` true for every `gerti.*` table (`select relname,relrowsecurity,relforcerowsecurity from pg_class join pg_namespace n on n.oid=relnamespace where nspname='gerti' and relkind='r';`).
  - `make test` (Znuny suite) → `FAIL=0`.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation | GO / NO-GO |
|---|---|---|---|---|
| D1 SQL mutates Znuny `public` data | Low | Critical | SQL has zero `DROP`/zero writes to public/znuny; only `CREATE … IF NOT EXISTS` + GRANT + ALTER ROLE; reviewed line-by-line; run via one-shot, non-`restart` | NO-GO if any statement targets `public`/`znuny` tables or lacks `IF NOT EXISTS`/idempotency |
| RLS not actually enforced on shared cluster (gerti_sidecar inherits a BYPASSRLS role) | Low | Critical | `gerti_sidecar` is `IN ROLE gerti_app` only (NOLOGIN, no BYPASSRLS); FORCE RLS on every table; prod verification query asserts 0 rows unset-GUC | NO-GO if unset-GUC query returns >0 rows |
| Downtime to live Znuny during deploy | Very low | High | sidecar/migrate are additive `profiles:["gerti"]` services; `make up` of Znuny stack unaffected; postgres not restarted; no Znuny container rebuilt | NO-GO if any Znuny container restarts |
| Secrets in compose/env | Medium | High | `GERTI_*_DB_PASSWORD` only in gitignored `.env.prod`; psql vars quote-injected once; no password in image/logs; `.env.prod.example` documents keys with placeholders | NO-GO if a real secret appears in a tracked file |
| Migration not idempotent / partial apply | Low | Medium | Alembic linear chain audited (`0004`→`0009`); `sidecar-migrate` is `ON_ERROR_STOP`-equivalent (alembic aborts on first error); `service_completed_successfully` gates app start; rollback = `alembic downgrade -1` | NO-GO if `sidecar-migrate` exits non-zero |
| Append-only trigger blocks legitimate cycle close (H2) | Resolved | — | Trigger permits only `closing_cycle_id`/`glosa_id` UPDATE; e2e test proves close+adjust under RLS as unprivileged role before any deploy | NO-GO if #1C e2e not green locally |
| Matview leaks cross-tenant balances (RLS bypass) | Known/accepted | Medium | Matview is admin/reporting-only; no tenant path queries it; documented; tenant balance via `ConsumptionService.balance()` only | Accept; revisit when reporting API (#1E) ships |
| cloudflared ingress edit breaks `znuny-dev` hostname | Low | High | Append API rule; keep existing `znuny-dev → znuny-web:80` first; verify Znuny 200 immediately after | NO-GO if znuny-dev stops returning 200 |

## Human-needed (true blockers only)

1. **Cloudflare API token scope** — if the provided token lacks `Zone:DNS:Edit`, the `api-dev` DNS record must be created manually in the dashboard (D3 Step 2). Ingress (`cfd_tunnel` config) only needs `Cloudflare Tunnel:Edit`. **Non-blocking for code; blocks public reachability of `api-dev` until DNS exists.**
2. **Prod DB passwords** — `GERTI_SIDECAR_DB_PASSWORD` / `GERTI_ADMIN_DB_PASSWORD` must be set in `.env.prod` on the VPS before D1 Step 3. Autonomous agent should generate strong values and write them to `.env.prod` (gitignored) only; surface them to the human out-of-band.

Everything else is autonomous.
