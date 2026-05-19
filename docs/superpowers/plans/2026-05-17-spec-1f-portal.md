# Spec #1F-a — Portal Cliente white-label (vertical slice) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the white-label client portal end-to-end as a *vertical slice*: each Gerti tenant reaches `<tenant>.suporte.gerti.com.br`, sees a portal painted with **their** brand, logs in with a credential validated against the single Znuny (via the sidecar's Generic Interface — no OIDC), and sees **their** contracts + balances reusing the #1C `ConsumptionService.balance` engine, isolated per tenant by RLS. NOTHING from Spec §9 YAGNI (tickets, service catalog, dynamic forms, executive dashboards/KPIs, billing approval, branding admin UI, logo upload, i18n, multi-Znuny, OIDC/PKCE/`useOidc`) is built, scaffolded, or mentioned as a task.

**Architecture:** Extends the #1C sidecar (`apps/sidecar`, repo `ground-control` branch `main`, alembic chain head `0010_balance_view`, `TenantMiddleware` resolving `<sub>.suporte.gerti.com.br` to `request.state.tenant` + `app.current_tenant` GUC, FORCE RLS on every `gerti.*` table). Adds: one branding table (`gerti.tenant_branding`, 1:1 with tenant, same RLS template as #1C) read pre-auth under the subdomain GUC; a thin Znuny GI client `integrations/znuny_gi.py` (`authenticate_customer(login, password) -> bool`, raising `ZnunyUnavailable`) whose mechanism is **frozen by the Task 1 R1 spike**; a JWT HS256 session (`gsid` cookie) with a `get_current_session` dependency that fails closed and rejects cross-tenant cookies; five new routers (`/v1/branding`, `/v1/auth/login`, `/v1/auth/logout`, `/v1/me`, `/v1/contracts`) wired into `main.py` exactly like `health.router`; an idempotent `seed_demo_branding.py` mirroring `seed_demo_contracts.py` that seeds **TWO testable white-label tenants** (Aurora — branding only, tenant+contracts from #1C; and a new fictitious TechNova — its own `gerti.tenant`+branding+small contract set on the SAME single Znuny, plus a minimal Znuny `CustomerCompany`/`CustomerUser` test fixture via a sibling idempotent Perl seeder wired into `scripts/seed-demo.sh`); and a new Nuxt 3 SSR portal in `apps/portal/` that resolves branding server-side (Nitro middleware, no theme flash), proxies auth, and renders the tenant's contracts. The Nuxt layer NEVER talks to Znuny — the sidecar is the only door. New deploy is **additive**: a `portal` service under `profiles:["gerti"]` in the root `docker-compose.yml`, plus Cloudflare ingress for **both** `aurora.suporte.gerti.com.br` and `technova.suporte.gerti.com.br` via the documented read-modify-write pattern (the #1C D3 guard preserves `znuny-dev`+`api-dev`).

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, Pydantic v2, PyJWT (HS256), httpx (async, mocked in tests), pytest + pytest-asyncio + testcontainers (`postgres:18`); Nuxt 3 SSR, Nitro, @nuxt/ui v3, TailwindCSS, Pinia, TypeScript, Vitest + @nuxt/test-utils, pnpm (`--frozen-lockfile`); Docker Compose (additive profile), Cloudflare Tunnel (token-mode, multi-hostname).

---

## AUDIT — REAL CURRENT STATE (2026-05-17, verified by commands)

- **Repo:** `ground-control`, branch `main`, working tree has only `.playwright-mcp/` untracked. Root compose is `./docker-compose.yml` (NOT `infra/compose/...`).
- **Alembic chain head = `0010_balance_view`** (`apps/sidecar/alembic/versions/`: 0001..0010). New migration MUST be `down_revision="0010_balance_view"`, `revision="0011_tenant_branding"`.
- **Models present** (`models/__init__.py __all__`, alphabetical): `Base, ConsumptionEvent, Contract, ContractAdjustmentRule, ContractBillingParty, ContractCycle, ContractRenewalPolicy, ContractScopeCi, ContractScopeService, Glosa, ServiceCatalogItem, SharedCreditPool, Tenant, TicketContractLink, ZnunyInstance`. No branding model.
- **Sidecar seams confirmed:** `db.tenant_session_scope(tenant_id, *, factory=None)` (sets `SELECT set_config('app.current_tenant', :tid, true)`), `db.SessionLocal`, `db.get_tenant_session(request)`; `middleware/tenant.py` sets `request.state.tenant` (a `Tenant`), `META_PATHS` = `{/v1/health,/v1/openapi.json,/v1/docs,/v1/redoc}`, `ROOT_HOSTS` includes `testserver`; `config.py` `Settings(BaseSettings)` + `@lru_cache get_settings()`; `main.py` `create_app()` does `app.include_router(health.router, prefix=settings.api_v1_prefix)` then `app.add_middleware(TenantMiddleware)`.
- **`ConsumptionService(session).balance(contract_id) -> Balance`** exists; `Balance(kind: str, remaining: float | None)`, `kind` in `{"hours","brl","services","n/a"}`. Imported as `from gerti_sidecar.domain.consumption_service import ConsumptionService`.
- **conftest.py:** session-scoped `PostgresContainer("postgres:18", driver="asyncpg")` runs init SQL; `engine` applies Alembic head; `session` = admin (BYPASSRLS, rollback); `app_db_url`/`app_session_factory` = unprivileged `gerti_sidecar`; `seed_two_tenants`; autouse `_reset_settings_cache` does `get_settings.cache_clear()` before/after each test.
- **`test_rls_contract_tables.py::test_every_gerti_table_has_rls_enabled_and_forced`** enumerates ALL `gerti.*` base tables into an `expected` set and asserts `relrowsecurity AND relforcerowsecurity`. The S1 set MUST grow to include `tenant_branding`.
- **`seed_demo_contracts.py`:** argparse, `create_async_engine(os.environ["DATABASE_URL"])`, `async_sessionmaker`, importable `seed(s)` / `summary` / `reset`, check-before-insert by `Tenant.znuny_customer_id == "AURORA"`, thin `main()`. `AURORA_CUSTOMER_ID = "AURORA"`, subdomain `aurora`.
- **Gate baseline (verified):** `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q` -> **34 passed** (34 test functions across `tests/test_*.py`).
- **Latest ADR = D13** in `.ia/DECISIONS.md`. This plan adds **D14** (R1 auth mechanism, from the Task 1 spike), **D15** (portal deploy), and **D16** (TenantMiddleware resolves subdomain->tenant via a narrow BYPASSRLS identity path; all tenant data stays RLS-subject — authored in Task 3).
- **OPS access:** `ssh gc` (jump alias; direct Tailscale path is broken — see `.ia/OPS.md`). Cloudflare ingress = read-modify-write of the `cfd_tunnel` configuration (D3 of `2026-05-17-spec-1c-deploy.md`); whole-object PUT, splice before the `http_status:404` catch-all, abort-guard if existing hostname missing.

---

## Hardening applied

Static-analysis traps found against the audited code + Postgres/Nuxt/cookie semantics. Each fix is baked into the named task.

| # | Trap | Fix (mandatory) |
|---|---|---|
| H1 | New settings (`session_secret`, `session_cookie_name`, `session_ttl_seconds`) read via `@lru_cache get_settings()`; tests mutate env but the autouse `_reset_settings_cache` only clears the cache around each test — a settings access at import time of a router module would freeze stale config. | Settings accessed ONLY inside request handlers / dependencies via `Depends(get_settings)` or `get_settings()` at call-time (never at module import). Replicate #1C's pattern: no module-level `get_settings()` in any new router. conftest `_reset_settings_cache` handles cache-clear; new tests set env BEFORE constructing the app. (Task 4) |
| H2 | S1 invariant `test_every_gerti_table_has_rls_enabled_and_forced` enumerates ALL `gerti.*` tables; adding `tenant_branding` without extending `expected` makes it fail. | Add `"tenant_branding"` to the `expected` set in `test_rls_contract_tables.py`. Do NOT weaken the assertion. (Task 2) |
| H3 | `GET /v1/branding` on a host with no subdomain -> `TenantMiddleware` never sets `request.state.tenant`, GUC unset -> RLS 0 rows; naive `.scalar_one()` raises -> 500. Spec demands clean **404**. | Handler checks `getattr(request.state, "tenant", None)`; absent -> `HTTPException(404)`. Tenant resolved but no branding row -> still 404. Never 500. (Task 3) |
| H4 | Cookie set with `secure=True` is dropped by Starlette TestClient over plain HTTP; `samesite` must be lowercase. | Cookie attrs from settings; `ENVIRONMENT=test` => `secure=False` (config property `session_cookie_secure`: False when dev/test, else True); `httponly=True`, `samesite="lax"` always. (Tasks 4, 6) |
| H5 | JWT `exp` must be int POSIX UTC; UUID-vs-str compare silently mismatches. | `exp = int((datetime.now(UTC)+timedelta(seconds=ttl)).timestamp())`; payload `tenant_id` stored as `str(tenant.id)`; cross-tenant check compares `payload["tenant_id"] == str(request.state.tenant.id)` (both `str`). (Tasks 4, 6) |
| H6 | `get_current_session` must distinguish "no tenant / bad cookie" (401) from "valid cookie wrong tenant" (403). | Order: (a) tenant resolved? no -> 401; (b) `gsid` present+decodable+unexpired? no -> 401; (c) `payload.tenant_id == str(tenant.id)`? no -> 403; else inject. (Task 4) |
| H7 | The Znuny GI client must raise typed `ZnunyUnavailable` on transport failure (-> 503) and return `bool` for validity (-> 401 on `False`). No network in testcontainers. | `authenticate_customer(login, password) -> bool` raises `ZnunyUnavailable` ONLY on transport/5xx; `False` on auth-reject, `True` on success. All tests monkeypatch/mock httpx — zero network. (Tasks 1, 5, 6) |
| H8 | Nuxt SSR must forward inbound `Cookie` and re-emit the sidecar `Set-Cookie` as first-party for the subdomain, else session is lost. | `server/utils/sidecar.ts` forwards `cookie`+`host`; `server/api/auth/login.post.ts` copies sidecar `set-cookie` onto the Nuxt response. (Tasks 9, 11) |
| H9 | Behind cloudflared the inbound `Host` is the tunnel hostname; real host is `X-Forwarded-Host`. | Nitro middleware reads `X-Forwarded-Host` first, falls back to `Host`; forwarded value is sent as `Host` to the sidecar so `SUBDOMAIN_RE` matches. (Task 10) |
| H10 | Portal image builds on a host whose `app`/`data` nets are `internal:true` (offline runtime). | Multi-stage Dockerfile installs+builds with network at BUILD time only; runtime stage runs prebuilt `.output` — zero network. (Task 14) |
| H11 | Client-side theme decision flashes default brand before hydration. | Theme tokens injected as CSS custom properties into the SSR head via `useHead` server-side from `event.context.branding`; no client-side branding fetch. (Tasks 10, 12) |
| H12 | Branding cache must be keyed per subdomain with TTL or brands leak / go stale. | In-memory `Map<subdomain,{data,exp}>`, 60s TTL, key = resolved subdomain; failure -> neutral default (NOT cached as success). (Task 10) |
| H13 | `pnpm install` without a committed lockfile is non-reproducible; the offline build needs `--frozen-lockfile`. | `pnpm-lock.yaml` generated+committed in Task 9; every portal gate uses `pnpm -C apps/portal install --frozen-lockfile`. (Tasks 9, 14) |
| H14 | R1 (validate Znuny customer credential with NO GertiHooks/#1B) is highest risk; building auth before it is decided causes rework. | Task 1 is a BLOCKING spike with concrete `ssh gc` commands, decision criteria, read-only-schema FALLBACK, and a FROZEN function contract recorded as ADR **D14**. No later task starts until D14 is written. (Task 1) |
| H15 | `TenantMiddleware.dispatch` runs `select(Tenant).where(subdomain==...)` with no `app.current_tenant` GUC; in prod the sidecar connects as `gerti_sidecar` (RLS-subject, BYPASSRLS NOT inherited via role membership — #1C) and `gerti.tenant` is FORCE RLS, so the lookup returns 0 rows -> `tenant is None` -> **404 for every valid subdomain** (prod bug + every router test that binds `db.SessionLocal=app_session_factory` silently asserts 404). #1F is the first feature to exercise HTTP tenant-resolution in prod (in #1C only `/v1/health`, a META_PATH, ran). | Introduce a narrow BYPASSRLS read path used ONLY for subdomain->tenant resolution (`config.database_admin_url` optional, `db.admin_engine`/`db.AdminSessionLocal`, `TenantMiddleware` uses `AdminSessionLocal` if not None else `SessionLocal`; all tenant DATA stays RLS-subject via `tenant_session_scope`). Tests mirror `test_tenant_middleware.py`: bind `db.AdminSessionLocal` (the resolution path) to the admin `engine` while the data path exercises RLS. Prod compose sets `DATABASE_ADMIN_URL` from `gerti_admin_user`+`${GERTI_ADMIN_DB_PASSWORD:-}`. ADR **D16**. (Task 3) |
| H16 | The vertical slice must deliver TWO testable white-label tenants so cross-tenant isolation is demonstrable, not asserted on faith. TechNova (the 2nd tenant) needs its OWN `gerti.tenant` + `tenant_branding` + a small contract set, AND a minimal Znuny `CustomerCompany`/`CustomerUser` so `POST /v1/auth/login` validates against the real Znuny for tenant 2 (Aurora already has these from #1C). Both subdomains must be provisioned in the SAME D3 read-modify-write splice while preserving `znuny-dev`+`api-dev`. | 2 test tenants: TechNova needs its own `gerti.tenant` + branding + contracts + a minimal Znuny CustomerCompany/CustomerUser for real login; cross-tenant cookie rejection is the white-label proof; both subdomains provisioned in one D3 splice preserving znuny-dev+api-dev. `seed_demo_branding.seed()` returns `(aurora_id, technova_id)`, seeds Aurora branding only + the full TechNova tenant (same single `znuny_instance` — §2.1) reusing `seed_demo_contracts`' uuid5/append-only-safe pattern; `scripts/seed-technova.pl` (idempotent, 1 company + 1 user `admin.tech@technova.example` / `TechNova@Demo2026`) wired into `scripts/seed-demo.sh`; Task 14 splices BOTH hostnames before the `http_status:404` catch-all with the #1C D3 abort-guard asserting `znuny-dev`+`api-dev` survive; Task 13 e2e asserts different branding per subdomain, per-tenant contract isolation, and cross-tenant `gsid` rejection 403. (Tasks 8, 13, 14) |

---

## Domain & contract invariants (single source of truth — do not diverge)

- **Frozen Znuny GI contract (output of Task 1, recorded as D14):**
  ```python
  # apps/sidecar/src/gerti_sidecar/integrations/znuny_gi.py
  class ZnunyUnavailable(RuntimeError): ...
  async def authenticate_customer(login: str, password: str) -> bool: ...
  ```
  `True` = credential valid; `False` = rejected by Znuny; raises `ZnunyUnavailable` ONLY on transport/connect/timeout/5xx. Endpoint/token come from the single `gerti.znuny_instance` row (`base_url`, `webservice_token_secret_ref`).
- **Session payload:** `{"tenant_id": str(tenant.id), "customer_login": <login>, "exp": <int posix utc>}`, JWT HS256, secret = `settings.session_secret`, cookie = `settings.session_cookie_name` (`"gsid"`).
- **Cross-tenant defense:** `get_current_session` -> **403** if `payload["tenant_id"] != str(request.state.tenant.id)`; **401** if no tenant resolved or cookie missing/invalid/expired. RLS remains the data defense (fail-closed without GUC).
- **Names IDENTICAL across all tasks:** `tenant_branding`, `0011_tenant_branding`, `authenticate_customer`, `ZnunyUnavailable`, `get_current_session`, `gsid`, `seed` (from `seed_demo_branding`), `Balance.kind`/`Balance.remaining`, `tenant_session_scope`, `ConsumptionService`.

---

## Sidecar gate (run verbatim where stated)

```
cd /home/will/projetos/ground-control/apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q
```
Baseline: **34 passed**. Expected count stated after each sidecar task.

## Portal gate (run verbatim where stated)

```
pnpm -C apps/portal install --frozen-lockfile && pnpm -C apps/portal lint && pnpm -C apps/portal test run && pnpm -C apps/portal build
```

---

## Task 1 — R1 SPIKE (BLOCKING): decide & freeze the Znuny customer-auth mechanism

**Goal:** Decide, by concrete investigation against the live prod Znuny via `ssh gc`, HOW the sidecar validates a Znuny *customer* credential WITHOUT GertiHooks/#1B, then FREEZE the `authenticate_customer` contract and record it as ADR **D14**. No later task may begin until D14 exists.

**Files:** Modify `.ia/DECISIONS.md` (append D14) · Create `docs/superpowers/spikes/2026-05-17-r1-znuny-customer-auth.md` (evidence log).

- [ ] **Step 1 — Inventory existing Znuny webservices (read-only).** Run:
  ```
  ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List"'
  ```
  Record the list. For any webservice, dump it: `... Admin::WebService::Dump <ID>`.
- [ ] **Step 2 — Probe the Znuny 7.2.3 core Session GI operation.** Znuny core ships a `Session::SessionCreate` Generic Interface operation accepting a customer login + password, returning a `SessionID` on valid credentials. Confirm the module exists:
  ```
  ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "ls /opt/otrs/Kernel/GenericInterface/Operation/Session/"'
  ```
  Expected: `SessionCreate.pm` (+ `SessionGet.pm`) — proves a webservice exposing `Session::SessionCreate` over REST can be imported via SysConfig/webservice import with NO custom .opm (core code, not GertiHooks/#1B).
- [ ] **Step 3 — Decision criteria (apply in order, FIRST that holds):**
  1. **PRIMARY:** `SessionCreate.pm` present -> mechanism = a Generic Interface REST webservice (provider) exposing `Session::SessionCreate`, route `POST /Session`, mapped to the customer-login + password fields. `authenticate_customer` POSTs the JSON body; a body with a `SessionID` => `return True`; a body with `Error`/HTTP 4xx => `return False`; connect error/timeout/5xx => `raise ZnunyUnavailable`. Webservice created/imported server-side (config-only); access token stored under `gerti.znuny_instance.webservice_token_secret_ref`. Confirm exact customer-login field name with a one-off `curl` from inside the znuny-web container.
  2. **FALLBACK (documented, only if Step 2 shows no usable Session operation):** validate by a **read-only** query of the `znuny` schema: `SELECT pw FROM customer_user WHERE login = :login AND valid_id = 1`, hash the supplied password per Znuny's configured `Customer::AuthModule::DB::CryptType` (read the LIVE value via `bin/otrs.Console.pl Admin::Config::Read --setting-name "Customer::AuthModule::DB::CryptType"`; do not assume), compare constant-time. Read-only, no schema writes. Same `authenticate_customer` signature.
- [ ] **Step 4 — Record the decision.** Append a `## D14 — Validação de credencial de customer Znuny (R1, fatia #1F-a)` section to `.ia/DECISIONS.md` with Contexto, Decisão (PRIMARY or FALLBACK per the spike, exact route/operation OR table/CryptType), the frozen contract (`async def authenticate_customer(login: str, password: str) -> bool`, `class ZnunyUnavailable(RuntimeError)`, True/False/raise semantics, endpoint/token from the single `gerti.znuny_instance` row), and an Evidência pointer to the spike file. Write the real command transcripts into `docs/superpowers/spikes/2026-05-17-r1-znuny-customer-auth.md`.
- [ ] **Step 5 — Commit the spike artifacts.**
  ```
  cd /home/will/projetos/ground-control && git add .ia/DECISIONS.md docs/superpowers/spikes/2026-05-17-r1-znuny-customer-auth.md && git -c commit.gpgsign=false commit -m "spike(#1F-a): R1 — mecanismo de auth de customer Znuny + ADR D14"
  ```

**Gate:** No code gate (spike). Exit criterion: D14 written with a concrete decided mechanism + frozen contract; the spike evidence file contains real command output. Tasks 2–15 may now proceed.

---

## Task 2 — Migration `0011_tenant_branding` + model + RLS + S1 extension

**Files:** Create `apps/sidecar/alembic/versions/0011_tenant_branding.py` · Create `apps/sidecar/src/gerti_sidecar/models/tenant_branding.py` · Modify `apps/sidecar/src/gerti_sidecar/models/__init__.py` · Modify `apps/sidecar/tests/test_rls_contract_tables.py` · Create `apps/sidecar/tests/test_model_tenant_branding.py`.

- [ ] **Step 1 — Failing test (negative RLS + S1).** Add `"tenant_branding"` to the `expected` set in `test_rls_contract_tables.py` (set membership only). Create `tests/test_model_tenant_branding.py`:
  ```python
  """tenant_branding: 1:1 with tenant, RLS fail-closed, scoped by subdomain GUC."""

  from __future__ import annotations

  import pytest
  from sqlalchemy import text

  from gerti_sidecar import db
  from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


  @pytest.mark.asyncio
  async def test_tenant_branding_rls_fail_closed_and_scoped(session, app_session_factory):
      inst = ZnunyInstance(
          name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
      )
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="A SA", trade_name="A", document="1",
                 znuny_customer_id="a", znuny_instance_id=inst.id, subdomain="a")
      b = Tenant(legal_name="B SA", trade_name="B", document="2",
                 znuny_customer_id="b", znuny_instance_id=inst.id, subdomain="b")
      session.add_all([a, b])
      await session.flush()
      session.add_all([
          TenantBranding(tenant_id=a.id, display_name="Brand A"),
          TenantBranding(tenant_id=b.id, display_name="Brand B"),
      ])
      await session.commit()

      async with db.tenant_session_scope(a.id, factory=app_session_factory) as s:
          names = (await s.execute(
              text("SELECT display_name FROM gerti.tenant_branding"))).scalars().all()
      assert names == ["Brand A"]

      async with app_session_factory() as s:
          rows = (await s.execute(
              text("SELECT display_name FROM gerti.tenant_branding"))).scalars().all()
      assert rows == []
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_model_tenant_branding.py` -> `ImportError: cannot import name 'TenantBranding'`.
- [ ] **Step 3 — Migration (RLS template reproduced VERBATIM from `0005`/`0009`).** Create `apps/sidecar/alembic/versions/0011_tenant_branding.py`:
  ```python
  """tenant_branding (1:1 with tenant) with the per-tenant RLS template

  Revision ID: 0011_tenant_branding
  Revises: 0010_balance_view
  Create Date: 2026-05-17
  """

  from __future__ import annotations

  from collections.abc import Sequence

  import sqlalchemy as sa
  from sqlalchemy.dialects import postgresql

  from alembic import op

  revision: str = "0011_tenant_branding"
  down_revision: str | None = "0010_balance_view"
  branch_labels: str | Sequence[str] | None = None
  depends_on: str | Sequence[str] | None = None


  def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
      op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
      op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
      op.execute(
          f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
          f"USING ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
          f"WITH CHECK ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
      )
      op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


  def _disable_tenant_rls(table: str) -> None:
      op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
      op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
      op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
      op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")


  def upgrade() -> None:
      op.create_table(
          "tenant_branding",
          sa.Column(
              "tenant_id",
              postgresql.UUID(as_uuid=True),
              sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
              primary_key=True,
          ),
          sa.Column("display_name", sa.String(), nullable=False),
          sa.Column("logo_url", sa.String()),
          sa.Column("primary_color", sa.String(), nullable=False,
                    server_default=sa.text("'#2563EB'")),
          sa.Column("accent_color", sa.String(), nullable=False,
                    server_default=sa.text("'#1E40AF'")),
          sa.Column("default_theme", sa.String(), nullable=False,
                    server_default=sa.text("'light'")),
          sa.Column("support_email", sa.String()),
          sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                    server_default=sa.text("now()")),
          sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                    server_default=sa.text("now()")),
          sa.CheckConstraint("default_theme IN ('light','dark')",
                             name="ck_tenant_branding_theme"),
          schema="gerti",
      )
      _enable_tenant_rls("tenant_branding")
      op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


  def downgrade() -> None:
      _disable_tenant_rls("tenant_branding")
      op.drop_table("tenant_branding", schema="gerti")
  ```
- [ ] **Step 4 — Model.** Create `apps/sidecar/src/gerti_sidecar/models/tenant_branding.py`:
  ```python
  """Modelo TenantBranding — white-label 1:1 com o tenant."""

  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from gerti_sidecar.models.base import Base


  class TenantBranding(Base):
      __tablename__ = "tenant_branding"
      __table_args__ = (
          CheckConstraint("default_theme IN ('light','dark')",
                          name="ck_tenant_branding_theme"),
      )

      tenant_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True),
          ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
          primary_key=True,
      )
      display_name: Mapped[str] = mapped_column(String, nullable=False)
      logo_url: Mapped[str | None] = mapped_column(String)
      primary_color: Mapped[str] = mapped_column(
          String, nullable=False, server_default=text("'#2563EB'"))
      accent_color: Mapped[str] = mapped_column(
          String, nullable=False, server_default=text("'#1E40AF'"))
      default_theme: Mapped[str] = mapped_column(
          String, nullable=False, server_default=text("'light'"))
      support_email: Mapped[str | None] = mapped_column(String)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), nullable=False, server_default=func.now())
      updated_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), nullable=False,
          server_default=func.now(), onupdate=func.now())
  ```
- [ ] **Step 5 — Register model.** Modify `models/__init__.py`: add `from gerti_sidecar.models.tenant_branding import TenantBranding` (after the `tenant` import line) and insert `"TenantBranding",` into `__all__` alphabetically (after `"Tenant",`, before `"TicketContractLink",`).
- [ ] **Step 6 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **35 passed** (S1 stays green with the extended set).
- [ ] **Step 7 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/alembic/versions/0011_tenant_branding.py apps/sidecar/src/gerti_sidecar/models/tenant_branding.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/tests/test_model_tenant_branding.py apps/sidecar/tests/test_rls_contract_tables.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): migration 0011 tenant_branding + modelo + RLS + S1"
  ```

---

## Task 3 — TenantMiddleware BYPASSRLS lookup path (ADR D16) + `GET /v1/branding` router (unauthenticated, subdomain-scoped, 404-not-500)

**Files:** Modify `apps/sidecar/src/gerti_sidecar/config.py` · Modify `apps/sidecar/src/gerti_sidecar/db.py` · Modify `apps/sidecar/src/gerti_sidecar/middleware/tenant.py` · Modify `.ia/DECISIONS.md` (append D16) · Create `apps/sidecar/src/gerti_sidecar/routers/branding.py` · Modify `apps/sidecar/src/gerti_sidecar/main.py` · Create `apps/sidecar/tests/test_tenant_resolution_admin_path.py` · Create `apps/sidecar/tests/test_branding_router.py`.

> **WHY this is here (the gate critical defect, H15):** `TenantMiddleware.dispatch` resolves the tenant with `select(Tenant).where(Tenant.subdomain==..., Tenant.status=="active")` using `db.SessionLocal()` and **no `app.current_tenant` GUC set**. `gerti.tenant` is FORCE ROW LEVEL SECURITY with policy `id = NULLIF(current_setting('app.current_tenant', true),'')::uuid` (`0003_force_rls_tenant.py`). In prod the sidecar connects as `gerti_sidecar` (RLS-subject, BYPASSRLS NOT inherited via role membership — verified in #1C), so the lookup returns 0 rows -> `tenant is None` -> the middleware returns **404 for every valid subdomain**. This is a real prod bug (#1F is the first feature to exercise HTTP tenant-resolution in prod — in #1C only `/v1/health`, a META_PATH, ran) AND it makes every router test that binds `db.SessionLocal=app_session_factory` silently assert 404 instead of 200/401. Subdomain->tenant resolution is inherently a pre-auth cross-tenant *directory* lookup that reads only tenant identity, never tenant data — so it gets a narrow BYPASSRLS path; all tenant DATA stays RLS-subject via `tenant_session_scope`. The proven pattern is `tests/test_tenant_middleware.py` (binds `db.SessionLocal` to the admin `engine`). This task introduces the path, fixes the middleware, and rewires every router test (Tasks 3, 4, 6, 7, 13) to mirror it.

### Sub-section 3A — BYPASSRLS resolution path + D16

- [ ] **Step 1 — Failing test (admin path).** Create `apps/sidecar/tests/test_tenant_resolution_admin_path.py`:
  ```python
  """TenantMiddleware resolves subdomain via a BYPASSRLS path; data stays RLS.

  AdminSessionLocal (admin engine, BYPASSRLS) resolves the subdomain ->
  Tenant directory lookup; the route's tenant_session_scope data session
  stays RLS-subject (gerti_sidecar) and is still fail-closed without GUC.
  """

  from __future__ import annotations

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


  @pytest.mark.asyncio
  async def test_tenant_resolution_uses_admin_path(
      engine, app_session_factory, session
  ):
      inst = ZnunyInstance(
          name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
      )
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(t)
      await session.flush()
      session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
      await session.commit()

      # Resolution path = admin engine (BYPASSRLS); data path = RLS-subject.
      db.AdminSessionLocal = async_sessionmaker(
          engine, expire_on_commit=False, class_=AsyncSession)
      db.SessionLocal = app_session_factory
      app = create_app()
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as c:
          # valid subdomain resolves (200-class, NOT 404) because the
          # directory lookup goes through the BYPASSRLS path
          ok = await c.get("/v1/branding",
                           headers={"host": "aurora.suporte.gerti.com.br"})
          assert ok.status_code == 200
          assert ok.json()["display_name"] == "Aurora Móveis"

      # RLS still fail-closed on tenant DATA without the GUC (proves the
      # narrow path did NOT widen the data plane).
      async with app_session_factory() as s:
          rows = (await s.execute(
              text("SELECT display_name FROM gerti.tenant_branding"))).scalars().all()
      assert rows == []
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_tenant_resolution_admin_path.py` -> `AttributeError: module 'gerti_sidecar.db' has no attribute 'AdminSessionLocal'`.
- [ ] **Step 3 — Settings.** Modify `config.py`: add inside `Settings` (after `database_url`):
  ```python
      # admin DSN usado SÓ pela resolução subdomínio->tenant (BYPASSRLS,
      # somente identidade — ver D16). Opcional: ausente => cai no
      # SessionLocal normal (dev/test ligam SessionLocal ao admin engine).
      database_admin_url: PostgresDsn | None = None
  ```
  and a validator next to `must_be_async_dsn`:
  ```python
      @field_validator("database_admin_url")
      @classmethod
      def admin_must_be_async_dsn(cls, v: PostgresDsn | None) -> PostgresDsn | None:
          if v is None:
              return v
          scheme = str(v).split(":", 1)[0]
          if scheme != "postgresql+asyncpg":
              raise ValueError(
                  f"database_admin_url deve usar driver asyncpg (got {scheme}); "
                  "use 'postgresql+asyncpg://...'"
              )
          return v
  ```
  Setting is accessed ONLY via `init_db(settings)` at lifespan time (never at module import) — same discipline as H1; conftest's autouse `_reset_settings_cache` + new tests setting env before constructing the app keep the `@lru_cache get_settings()` honest.
- [ ] **Step 4 — DB engine.** Modify `apps/sidecar/src/gerti_sidecar/db.py`:
  - Add module globals next to `engine`/`SessionLocal`:
    ```python
    admin_engine: AsyncEngine | None = None
    AdminSessionLocal: async_sessionmaker[AsyncSession] | None = None
    ```
  - In `init_db`, after creating `engine`/`SessionLocal`, add (and extend the `global`):
    ```python
    def init_db(settings: Settings) -> None:
        """Inicializa engine e session factory globais a partir das settings."""
        global engine, SessionLocal, admin_engine, AdminSessionLocal
        engine = make_engine(settings)
        SessionLocal = make_session_factory(engine)
        if settings.database_admin_url is not None:
            admin_engine = create_async_engine(
                str(settings.database_admin_url),
                echo=settings.debug,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=2,
                pool_recycle=1800,
            )
            AdminSessionLocal = make_session_factory(admin_engine)
        else:
            admin_engine = None
            AdminSessionLocal = None
    ```
  - In `dispose_db`, dispose the admin engine too:
    ```python
    async def dispose_db() -> None:
        """Fecha o pool de conexões; chamar no shutdown."""
        global engine, SessionLocal, admin_engine, AdminSessionLocal
        if engine is not None:
            await engine.dispose()
        if admin_engine is not None:
            await admin_engine.dispose()
        engine = None
        SessionLocal = None
        admin_engine = None
        AdminSessionLocal = None
    ```
- [ ] **Step 5 — Middleware.** Modify `apps/sidecar/src/gerti_sidecar/middleware/tenant.py`: replace the resolution-session block ONLY (the `if db.SessionLocal is None: ... async with db.SessionLocal() as session:` lines) with:
  ```python
          # Resolução subdomínio->tenant é um lookup de DIRETÓRIO pré-auth
          # (só identidade, nunca dado de tenant). gerti.tenant é FORCE RLS;
          # sem GUC um session RLS-subject retornaria 0 linhas (404 falso).
          # Usa o caminho BYPASSRLS estreito quando configurado (D16); todo
          # DADO de tenant continua RLS-subject via tenant_session_scope.
          resolver = db.AdminSessionLocal or db.SessionLocal
          if resolver is None:
              raise RuntimeError("DB não inicializado")

          async with resolver() as session:
              result = await session.execute(
                  select(Tenant).where(Tenant.subdomain == subdomain, Tenant.status == "active")
              )
              tenant = result.scalar_one_or_none()
              if tenant is None:
  ```
  (The rest of the `dispatch` body — the 404 `JSONResponse`, `request.state.tenant = tenant`, `call_next`, `x-gerti-tenant` header — is unchanged; only the session factory selection changes. Nothing else in the file changes.)
- [ ] **Step 6 — Author ADR D16.** Append to `.ia/DECISIONS.md` a `## D16 — TenantMiddleware resolve subdomínio->tenant por um caminho BYPASSRLS estreito (somente identidade); todo dado de tenant permanece RLS-subject` section: **Contexto** — `gerti.tenant` é FORCE RLS (D-0003); em prod o sidecar conecta como `gerti_sidecar` (RLS-subject, BYPASSRLS não herdado via role membership — #1C); o `TenantMiddleware` resolve o subdomínio ANTES de qualquer GUC, então um session RLS-subject retorna 0 linhas e 404 para todo tenant válido. **Decisão** — introduzir `Settings.database_admin_url` (opcional), `db.admin_engine`/`db.AdminSessionLocal` (criados em `init_db` quando o DSN existe, descartados em `dispose_db`); `TenantMiddleware` usa `AdminSessionLocal or SessionLocal` SÓ para o `select(Tenant).where(subdomain==...)` (lookup de diretório, só identidade); todo DADO de tenant continua RLS-subject via `tenant_session_scope`. Prod: compose injeta `DATABASE_ADMIN_URL` do `gerti_admin_user`+`${GERTI_ADMIN_DB_PASSWORD:-}` (nunca `${VAR:?}` — footgun D13). Dev/test sem DSN admin: `AdminSessionLocal=None` => cai no `SessionLocal` (que os testes ligam ao admin engine, como `test_tenant_middleware.py`). **Evidência** — `test_tenant_resolution_admin_path.py` (subdomínio válido resolve 200-class via path BYPASSRLS; RLS ainda fail-closed no dado).
- [ ] **Step 7 — Run, expect pass (admin path).** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_tenant_resolution_admin_path.py` -> passes (depends on Sub-section 3B's router existing; if run before 3B, expect route-missing — run the full **Sidecar gate** at Step 6 of 3B).

### Sub-section 3B — `GET /v1/branding` router

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_branding_router.py`:
  ```python
  """GET /v1/branding: subdomain-scoped, no auth, 404 on root/unknown host.

  Mirrors test_tenant_middleware.py: the subdomain->tenant resolution path
  is bound to the admin `engine` (BYPASSRLS) via db.AdminSessionLocal so the
  FORCE-RLS gerti.tenant lookup succeeds; the tenant DATA path
  (db.SessionLocal=app_session_factory) stays RLS-subject and is exercised
  under the app.current_tenant GUC set by tenant_session_scope.
  """

  from __future__ import annotations

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


  @pytest.mark.asyncio
  async def test_branding_resolves_by_subdomain_and_404_on_root(
      engine, app_session_factory, session
  ):
      inst = ZnunyInstance(
          name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
      )
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(t)
      await session.flush()
      session.add(TenantBranding(
          tenant_id=t.id, display_name="Aurora Móveis",
          primary_color="#0EA5E9", support_email="suporte@aurora.example"))
      await session.commit()

      # Resolution path = admin engine (BYPASSRLS); data path = RLS-subject.
      db.AdminSessionLocal = async_sessionmaker(
          engine, expire_on_commit=False, class_=AsyncSession)
      db.SessionLocal = app_session_factory
      app = create_app()
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as c:
          ok = await c.get("/v1/branding",
                           headers={"host": "aurora.suporte.gerti.com.br"})
          assert ok.status_code == 200
          body = ok.json()
          assert body["display_name"] == "Aurora Móveis"
          assert body["primary_color"] == "#0EA5E9"
          assert body["support_email"] == "suporte@aurora.example"

          root = await c.get("/v1/branding", headers={"host": "localhost"})
          assert root.status_code == 404
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_branding_router.py` -> route missing.
- [ ] **Step 3 — Router.** Create `apps/sidecar/src/gerti_sidecar/routers/branding.py`:
  ```python
  """GET /v1/branding — não autenticado, escopado por subdomínio (RLS).

  TenantMiddleware já setou request.state.tenant + app.current_tenant a
  partir do subdomínio. Host sem subdomínio -> sem tenant -> 404 limpo
  (Nuxt aplica tema default). Payload mínimo, sem dado sensível.
  """

  from __future__ import annotations

  from fastapi import APIRouter, Depends, HTTPException, Request
  from pydantic import BaseModel
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from gerti_sidecar.db import get_tenant_session
  from gerti_sidecar.models import TenantBranding

  router = APIRouter(prefix="/branding", tags=["portal"])


  class BrandingResponse(BaseModel):
      display_name: str
      logo_url: str | None
      primary_color: str
      accent_color: str
      default_theme: str
      support_email: str | None


  def _require_tenant(request: Request) -> None:
      if getattr(request.state, "tenant", None) is None:
          raise HTTPException(status_code=404, detail="tenant_not_resolved")


  @router.get("", response_model=BrandingResponse)
  async def get_branding(
      request: Request,
      _: None = Depends(_require_tenant),
      session: AsyncSession = Depends(get_tenant_session),
  ) -> BrandingResponse:
      row = (await session.execute(select(TenantBranding))).scalar_one_or_none()
      if row is None:
          raise HTTPException(status_code=404, detail="branding_not_found")
      return BrandingResponse(
          display_name=row.display_name,
          logo_url=row.logo_url,
          primary_color=row.primary_color,
          accent_color=row.accent_color,
          default_theme=row.default_theme,
          support_email=row.support_email,
      )
  ```
- [ ] **Step 4 — Wire router.** Modify `main.py`: change import to `from gerti_sidecar.routers import branding, health` and after the existing `app.include_router(health.router, prefix=settings.api_v1_prefix)` add `app.include_router(branding.router, prefix=settings.api_v1_prefix)`.
- [ ] **Step 5 — Run, expect pass (full task gate).** Run the **Sidecar gate** verbatim. Expected: **37 passed** (Task 2's 35 + the admin-path test from 3A + the branding router test from 3B = +2).
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/config.py apps/sidecar/src/gerti_sidecar/db.py apps/sidecar/src/gerti_sidecar/middleware/tenant.py .ia/DECISIONS.md apps/sidecar/src/gerti_sidecar/routers/branding.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_tenant_resolution_admin_path.py apps/sidecar/tests/test_branding_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): BYPASSRLS lookup do TenantMiddleware (ADR D16) + GET /v1/branding subdomain-scoped (404 em host raiz)"
  ```

---

## Task 4 — Auth core: settings, JWT session, `get_current_session`, `GET /v1/me`

**Files:** Modify `apps/sidecar/src/gerti_sidecar/config.py` · Create `apps/sidecar/src/gerti_sidecar/auth/__init__.py` · Create `apps/sidecar/src/gerti_sidecar/auth/session.py` · Create `apps/sidecar/src/gerti_sidecar/routers/me.py` · Modify `apps/sidecar/src/gerti_sidecar/main.py` · Modify `apps/sidecar/pyproject.toml` · Create `apps/sidecar/tests/test_auth_session.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_auth_session.py`:
  ```python
  """JWT session: encode/decode, /v1/me, no-tenant 401, wrong-tenant 403."""

  from __future__ import annotations

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


  @pytest.mark.asyncio
  async def test_me_requires_matching_tenant(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(t)
      await session.flush()
      session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
      await session.commit()

      # Resolution path = admin engine (BYPASSRLS, mirrors
      # test_tenant_middleware.py); data path = RLS-subject (gerti_sidecar).
      db.AdminSessionLocal = async_sessionmaker(
          engine, expire_on_commit=False, class_=AsyncSession)
      db.SessionLocal = app_session_factory
      app = create_app()
      st = get_settings()
      good = encode_session(str(t.id), "joe", st)
      bad = encode_session("00000000-0000-0000-0000-000000000000", "x", st)
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as c:
          h = {"host": "aurora.suporte.gerti.com.br"}
          assert (await c.get("/v1/me", headers=h)).status_code == 401
          c.cookies.set("gsid", bad)
          assert (await c.get("/v1/me", headers=h)).status_code == 403
          c.cookies.set("gsid", good)
          ok = await c.get("/v1/me", headers=h)
          assert ok.status_code == 200
          assert ok.json()["customer_login"] == "joe"
          assert ok.json()["display_name"] == "Aurora Móveis"
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_auth_session.py` -> `ModuleNotFoundError: gerti_sidecar.auth`.
- [ ] **Step 3 — Add dependency.** Modify `pyproject.toml`: add `"pyjwt>=2.9"` to `[project].dependencies`. Run `cd /home/will/projetos/ground-control/apps/sidecar && uv lock && uv sync --all-extras`.
- [ ] **Step 4 — Settings.** Modify `config.py`: add inside `Settings` (after `database_url`):
  ```python
      # portal session (Spec #1F-a) ------------------------------------
      session_secret: str = "dev-insecure-session-secret-change-me"
      session_cookie_name: str = "gsid"
      session_ttl_seconds: int = 28800  # 8h
  ```
  and a property next to `is_test`:
  ```python
      @property
      def session_cookie_secure(self) -> bool:
          # Plain-HTTP test/dev clients drop Secure cookies (H4).
          return self.environment not in ("development", "test")
  ```
  No module-level `get_settings()` is introduced anywhere (H1).
- [ ] **Step 5 — Auth package.** Create `apps/sidecar/src/gerti_sidecar/auth/__init__.py` (empty). Create `apps/sidecar/src/gerti_sidecar/auth/session.py`:
  ```python
  """Sessão de portal: JWT HS256 assinado + dependency anti cross-tenant.

  Payload: {tenant_id (str), customer_login (str), exp (int posix utc)}.
  get_current_session: 401 se sem tenant / cookie ausente|inválido|expirado;
  403 se o tenant do cookie != tenant do subdomínio (request.state.tenant).
  """

  from __future__ import annotations

  import datetime as dt
  from typing import TypedDict

  import jwt
  from fastapi import Depends, HTTPException, Request

  from gerti_sidecar.config import Settings, get_settings

  _ALG = "HS256"


  class SessionPayload(TypedDict):
      tenant_id: str
      customer_login: str
      exp: int


  def encode_session(tenant_id: str, customer_login: str, settings: Settings) -> str:
      exp = int(
          (dt.datetime.now(dt.UTC)
           + dt.timedelta(seconds=settings.session_ttl_seconds)).timestamp()
      )
      payload: SessionPayload = {
          "tenant_id": tenant_id,
          "customer_login": customer_login,
          "exp": exp,
      }
      return jwt.encode(dict(payload), settings.session_secret, algorithm=_ALG)


  def decode_session(token: str, settings: Settings) -> SessionPayload | None:
      try:
          data = jwt.decode(token, settings.session_secret, algorithms=[_ALG])
      except jwt.PyJWTError:
          return None
      if not isinstance(data.get("tenant_id"), str) or not isinstance(
          data.get("customer_login"), str
      ):
          return None
      return SessionPayload(
          tenant_id=data["tenant_id"],
          customer_login=data["customer_login"],
          exp=int(data["exp"]),
      )


  async def get_current_session(
      request: Request,
      settings: Settings = Depends(get_settings),
  ) -> SessionPayload:
      tenant = getattr(request.state, "tenant", None)
      if tenant is None:
          raise HTTPException(status_code=401, detail="no_session")
      token = request.cookies.get(settings.session_cookie_name)
      if not token:
          raise HTTPException(status_code=401, detail="no_session")
      payload = decode_session(token, settings)
      if payload is None:
          raise HTTPException(status_code=401, detail="invalid_session")
      if payload["tenant_id"] != str(tenant.id):
          raise HTTPException(status_code=403, detail="tenant_mismatch")
      return payload
  ```
- [ ] **Step 6 — `/v1/me` router.** Create `apps/sidecar/src/gerti_sidecar/routers/me.py`:
  ```python
  """GET /v1/me — sessão válida; devolve identidade + display_name do tenant."""

  from __future__ import annotations

  from fastapi import APIRouter, Depends, HTTPException
  from pydantic import BaseModel
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from gerti_sidecar.auth.session import SessionPayload, get_current_session
  from gerti_sidecar.db import get_tenant_session
  from gerti_sidecar.models import TenantBranding

  router = APIRouter(prefix="/me", tags=["portal"])


  class MeResponse(BaseModel):
      tenant_id: str
      display_name: str
      customer_login: str


  @router.get("", response_model=MeResponse)
  async def get_me(
      session_payload: SessionPayload = Depends(get_current_session),
      session: AsyncSession = Depends(get_tenant_session),
  ) -> MeResponse:
      row = (await session.execute(select(TenantBranding))).scalar_one_or_none()
      if row is None:
          raise HTTPException(status_code=404, detail="branding_not_found")
      return MeResponse(
          tenant_id=session_payload["tenant_id"],
          display_name=row.display_name,
          customer_login=session_payload["customer_login"],
      )
  ```
- [ ] **Step 7 — Wire router.** Modify `main.py`: import `from gerti_sidecar.routers import branding, health, me` and after the branding include add `app.include_router(me.router, prefix=settings.api_v1_prefix)`.
- [ ] **Step 8 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **38 passed**.
- [ ] **Step 9 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/pyproject.toml apps/sidecar/uv.lock apps/sidecar/src/gerti_sidecar/config.py apps/sidecar/src/gerti_sidecar/auth apps/sidecar/src/gerti_sidecar/routers/me.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_auth_session.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): sessão JWT HS256 + get_current_session + GET /v1/me"
  ```

---

## Task 5 — `integrations/znuny_gi.py` (Task-1-frozen `authenticate_customer`)

**Files:** Create `apps/sidecar/src/gerti_sidecar/integrations/__init__.py` · Create `apps/sidecar/src/gerti_sidecar/integrations/znuny_gi.py` · Create `apps/sidecar/tests/test_znuny_gi.py`.

> **Reconciliação D14:** o campo de login é `CustomerUserLogin` (auth de CUSTOMER), não `UserLogin` (auth de agente) — o plano foi escrito pré-spike; D14 é autoritativo.

> Implement the mechanism FROZEN in D14 (Task 1). The code below is the **PRIMARY** (`Session::SessionCreate` REST webservice) shape; if D14 chose the FALLBACK, implement the read-only `customer_user`/`CryptType` variant instead, keeping the IDENTICAL public signature `authenticate_customer(login, password) -> bool` + `ZnunyUnavailable`. Tests mock the HTTP — zero network in testcontainers (H7).

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_znuny_gi.py`:
  ```python
  """znuny_gi.authenticate_customer: True/False/ZnunyUnavailable, mocked HTTP."""

  from __future__ import annotations

  import httpx
  import pytest

  from gerti_sidecar.integrations import znuny_gi


  class _MockResp:
      def __init__(self, status_code: int, payload: dict) -> None:
          self.status_code = status_code
          self._payload = payload

      def json(self) -> dict:
          return self._payload


  @pytest.mark.asyncio
  async def test_authenticate_customer_paths(monkeypatch):
      captured: dict = {}

      async def ok_post(self, url, **kw):  # noqa: ANN001
          captured["json"] = kw.get("json")
          return _MockResp(200, {"SessionID": "abc"})

      async def reject_post(self, url, **kw):  # noqa: ANN001
          return _MockResp(200, {"Error": {"ErrorCode": "AuthFail"}})

      async def boom_post(self, url, **kw):  # noqa: ANN001
          raise httpx.ConnectError("down")

      monkeypatch.setattr(znuny_gi, "_resolve_endpoint",
                          lambda: ("http://znuny/ws", "tok"))

      monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
      assert await znuny_gi.authenticate_customer("joe", "pw") is True

      # D14 regression guard: customer-login body uses CustomerUserLogin
      # (Kernel::System::CustomerAuth) — never UserLogin (agent auth).
      body = captured["json"]
      assert body["CustomerUserLogin"] == "joe"
      assert "Password" in body
      assert "UserLogin" not in body

      monkeypatch.setattr(httpx.AsyncClient, "post", reject_post)
      assert await znuny_gi.authenticate_customer("joe", "bad") is False

      monkeypatch.setattr(httpx.AsyncClient, "post", boom_post)
      with pytest.raises(znuny_gi.ZnunyUnavailable):
          await znuny_gi.authenticate_customer("joe", "pw")
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_znuny_gi.py` -> import error.
- [ ] **Step 3 — Implement.** Create `apps/sidecar/src/gerti_sidecar/integrations/__init__.py` (empty). Create `apps/sidecar/src/gerti_sidecar/integrations/znuny_gi.py`:
  ```python
  """Cliente fino do Generic Interface do Znuny — só auth de customer.

  Contrato CONGELADO no spike R1 (ADR D14):
    authenticate_customer(login, password) -> bool
    ZnunyUnavailable: só em falha de transporte/5xx (nunca em rejeição limpa).
  Endpoint/token vêm da única linha gerti.znuny_instance.
  """

  from __future__ import annotations

  import os

  import httpx


  class ZnunyUnavailable(RuntimeError):
      """Falha de transporte ao falar com o Znuny (-> 503 no router)."""


  def _resolve_endpoint() -> tuple[str, str]:
      """(url do webservice, token de acesso). base_url da gerti.znuny_instance;
      o token concreto é resolvido do secret-ref (vault) — em dev/test cai no
      env ZNUNY_WS_URL / ZNUNY_WS_TOKEN. Implementação exata definida em D14."""
      url = os.environ.get("ZNUNY_WS_URL", "")
      token = os.environ.get("ZNUNY_WS_TOKEN", "")
      return url, token


  async def authenticate_customer(login: str, password: str) -> bool:
      url, token = _resolve_endpoint()
      body = {"CustomerUserLogin": login, "Password": password, "AccessToken": token}
      try:
          async with httpx.AsyncClient(timeout=10.0) as client:
              resp = await client.post(url, json=body)
      except httpx.HTTPError as exc:
          raise ZnunyUnavailable(str(exc)) from exc
      if resp.status_code >= 500:
          raise ZnunyUnavailable(f"znuny http {resp.status_code}")
      try:
          data = resp.json()
      except ValueError as exc:
          raise ZnunyUnavailable("resposta não-JSON do Znuny") from exc
      return bool(data.get("SessionID")) and "Error" not in data
  ```
- [ ] **Step 4 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **39 passed**.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/integrations apps/sidecar/tests/test_znuny_gi.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): integrations/znuny_gi.authenticate_customer (contrato D14)"
  ```

---

## Task 6 — `POST /v1/auth/login` + `POST /v1/auth/logout`

**Files:** Create `apps/sidecar/src/gerti_sidecar/routers/auth.py` · Modify `apps/sidecar/src/gerti_sidecar/main.py` · Create `apps/sidecar/tests/test_auth_login_router.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_auth_login_router.py`:
  ```python
  """POST /v1/auth/login: 200+cookie ok, 401 bad cred, 503 Znuny down; logout."""

  from __future__ import annotations

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance
  from gerti_sidecar.routers import auth as auth_router


  @pytest.mark.asyncio
  async def test_login_paths(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(t)
      await session.flush()
      session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
      await session.commit()
      # Resolution path = admin engine (BYPASSRLS, mirrors
      # test_tenant_middleware.py); data path = RLS-subject (gerti_sidecar).
      monkeypatch.setattr(
          db,
          "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
      )
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      h = {"host": "aurora.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)

      async def good(login, password):  # noqa: ANN001
          return True

      async def bad(login, password):  # noqa: ANN001
          return False

      async def down(login, password):  # noqa: ANN001
          raise auth_router.ZnunyUnavailable("down")

      async with AsyncClient(transport=transport, base_url="http://t") as c:
          monkeypatch.setattr(auth_router, "authenticate_customer", good)
          r = await c.post("/v1/auth/login", headers=h,
                           json={"username": "joe", "password": "pw"})
          assert r.status_code == 200
          assert "gsid" in r.cookies
          monkeypatch.setattr(auth_router, "authenticate_customer", bad)
          assert (await c.post("/v1/auth/login", headers=h,
                  json={"username": "x", "password": "y"})).status_code == 401
          monkeypatch.setattr(auth_router, "authenticate_customer", down)
          assert (await c.post("/v1/auth/login", headers=h,
                  json={"username": "x", "password": "y"})).status_code == 503
          out = await c.post("/v1/auth/logout", headers=h)
          assert out.status_code == 204
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_auth_login_router.py` -> route/module missing.
- [ ] **Step 3 — Router.** Create `apps/sidecar/src/gerti_sidecar/routers/auth.py`:
  ```python
  """POST /v1/auth/login + /v1/auth/logout — valida no Znuny GI, emite gsid."""

  from __future__ import annotations

  from fastapi import APIRouter, Depends, HTTPException, Request, Response
  from pydantic import BaseModel

  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import Settings, get_settings
  from gerti_sidecar.integrations.znuny_gi import (
      ZnunyUnavailable,
      authenticate_customer,
  )

  router = APIRouter(prefix="/auth", tags=["portal"])


  class LoginBody(BaseModel):
      username: str
      password: str


  @router.post("/login")
  async def login(
      body: LoginBody,
      request: Request,
      response: Response,
      settings: Settings = Depends(get_settings),
  ) -> dict[str, str]:
      tenant = getattr(request.state, "tenant", None)
      if tenant is None:
          raise HTTPException(status_code=404, detail="tenant_not_resolved")
      try:
          ok = await authenticate_customer(body.username, body.password)
      except ZnunyUnavailable as exc:
          raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
      if not ok:
          raise HTTPException(status_code=401, detail="invalid_credentials")
      token = encode_session(str(tenant.id), body.username, settings)
      response.set_cookie(
          key=settings.session_cookie_name,
          value=token,
          max_age=settings.session_ttl_seconds,
          httponly=True,
          secure=settings.session_cookie_secure,
          samesite="lax",
          path="/",
      )
      return {"status": "ok"}


  @router.post("/logout", status_code=204)
  async def logout(
      response: Response,
      settings: Settings = Depends(get_settings),
  ) -> Response:
      response.delete_cookie(
          key=settings.session_cookie_name,
          httponly=True,
          secure=settings.session_cookie_secure,
          samesite="lax",
          path="/",
      )
      response.status_code = 204
      return response
  ```
- [ ] **Step 4 — Wire router.** Modify `main.py`: import `from gerti_sidecar.routers import auth, branding, health, me` and after `me` add `app.include_router(auth.router, prefix=settings.api_v1_prefix)`.
- [ ] **Step 5 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **40 passed**.
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/auth.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_auth_login_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): POST /v1/auth/login + /logout (cookie gsid HttpOnly)"
  ```

> **Reconciliação (test-isolation):** binds de `db.*` via `monkeypatch.setattr` (auto-restore), não atribuição global — senão vazam p/ `test_tenant_middleware`; convenção descoberta no Task 3, plano escrito antes.

---

## Task 7 — `GET /v1/contracts` (authenticated, tenant-scoped, reuses #1C balance)

**Files:** Create `apps/sidecar/src/gerti_sidecar/routers/contracts.py` · Modify `apps/sidecar/src/gerti_sidecar/main.py` · Create `apps/sidecar/tests/test_contracts_router.py`.

> **RLS-exercise decision for `/v1/contracts` (chosen, explicit):** `get_tenant_session` runs `tenant_session_scope(tenant.id)` with NO `factory=`, so it uses module `db.SessionLocal`. The test binds `db.SessionLocal = app_session_factory` (the unprivileged RLS-subject `gerti_sidecar` role) and binds the SEPARATE `db.AdminSessionLocal` to the admin `engine` for subdomain resolution ONLY. Therefore the contracts read is genuinely served by the RLS-subject role under the `app.current_tenant` GUC — RLS is really exercised on the data path here; NO FastAPI dependency override is needed and the route is NOT covered by an admin factory for its data. The "200 via subdomain through middleware" assertion (resolution via the BYPASSRLS `AdminSessionLocal`) and the "RLS genuinely enforced on contract data" guarantee (data via the RLS-subject `SessionLocal`) are now on TWO distinct factories and no longer contradict each other (this is exactly the gate defect being fixed). Task 2 additionally pins direct RLS fail-closed for `tenant_branding` via `tenant_session_scope(..., factory=app_session_factory)`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_contracts_router.py`:
  ```python
  """GET /v1/contracts: auth required, tenant-scoped, balances via #1C."""

  from __future__ import annotations

  import datetime as dt

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
  from gerti_sidecar.models.enums import ContractType


  @pytest.mark.asyncio
  async def test_contracts_scoped_and_authed(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(t)
      await session.flush()
      session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
      session.add(Contract(tenant_id=t.id, code="AUR-1", type=ContractType.credit_brl,
          starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
          initial_amount_brl=10000, created_by="seed"))
      await session.commit()
      # Resolution path = admin engine (BYPASSRLS, mirrors
      # test_tenant_middleware.py). Data path: db.SessionLocal =
      # app_session_factory (RLS-subject). get_tenant_session ->
      # tenant_session_scope(tenant.id) (no factory=) uses module
      # db.SessionLocal, so /v1/contracts data is GENUINELY served by the
      # RLS-subject gerti_sidecar role under the app.current_tenant GUC —
      # RLS is really exercised on the contracts read (not bypassed).
      monkeypatch.setattr(
          db,
          "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
      )
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      h = {"host": "aurora.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as c:
          assert (await c.get("/v1/contracts", headers=h)).status_code == 401
          c.cookies.set("gsid", encode_session(str(t.id), "joe", st))
          r = await c.get("/v1/contracts", headers=h)
          assert r.status_code == 200
          rows = r.json()
          assert len(rows) == 1
          assert rows[0]["code"] == "AUR-1"
          assert rows[0]["saldo"]["kind"] == "brl"
          assert rows[0]["saldo"]["remaining"] == 10000.0
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contracts_router.py` -> route missing.
- [ ] **Step 3 — Router.** Create `apps/sidecar/src/gerti_sidecar/routers/contracts.py`:
  ```python
  """GET /v1/contracts — autenticado, tenant da sessão, saldo via #1C."""

  from __future__ import annotations

  import datetime as dt

  from fastapi import APIRouter, Depends
  from pydantic import BaseModel
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from gerti_sidecar.auth.session import SessionPayload, get_current_session
  from gerti_sidecar.db import get_tenant_session
  from gerti_sidecar.domain.consumption_service import ConsumptionService
  from gerti_sidecar.models import Contract

  router = APIRouter(prefix="/contracts", tags=["portal"])


  class Saldo(BaseModel):
      kind: str
      remaining: float | None


  class ContractItem(BaseModel):
      code: str
      type: str
      status: str
      starts_on: dt.date
      ends_on: dt.date
      saldo: Saldo


  @router.get("", response_model=list[ContractItem])
  async def list_contracts(
      _session_payload: SessionPayload = Depends(get_current_session),
      session: AsyncSession = Depends(get_tenant_session),
  ) -> list[ContractItem]:
      contracts = (
          await session.execute(select(Contract).order_by(Contract.code))
      ).scalars().all()
      cons = ConsumptionService(session)
      out: list[ContractItem] = []
      for c in contracts:
          bal = await cons.balance(c.id)
          out.append(
              ContractItem(
                  code=c.code,
                  type=c.type.value,
                  status=c.status.value,
                  starts_on=c.starts_on,
                  ends_on=c.ends_on,
                  saldo=Saldo(kind=bal.kind, remaining=bal.remaining),
              )
          )
      return out
  ```
- [ ] **Step 4 — Wire router.** Modify `main.py`: import `from gerti_sidecar.routers import auth, branding, contracts, health, me` and after `auth` add `app.include_router(contracts.router, prefix=settings.api_v1_prefix)`.
- [ ] **Step 5 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **41 passed**.
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/contracts.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_contracts_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-a): GET /v1/contracts (auth, tenant-scoped, saldo #1C)"
  ```

> **Reconciliação (test-isolation):** binds de `db.*` via `monkeypatch.setattr` (auto-restore) — convenção do Task 3; plano escrito antes.

---

## Task 8 — `seed_demo_branding.py` (idempotent, **2 white-label test tenants**: Aurora + TechNova) + Znuny TechNova customer fixture

**Scope note (approved breadth, NOT a §9 breach):** still strictly "branding + portal vertical slice", just delivered for **TWO** testable white-label tenants so cross-tenant white-label isolation is demonstrable. NO admin UI, NO onboarding automation, NO OIDC, NO tickets/catalog/dashboards. The 2nd tenant ("TechNova", fictitious) reuses the EXACT `seed_demo_contracts` Contract/Cycle/ConsumptionEvent model+pattern; the Znuny side gets a minimal 1-company/1-user fixture (test fixture like #1C's Aurora Znuny seed, NOT #1G onboarding).

**Tenant identities (frozen — spelled identically across Tasks 8, 13, 14):**
- **Aurora** — `znuny_customer_id='AURORA'`, `subdomain='aurora'`, tenant id `5effe6fd-005e-43e4-9b1a-81107eb7f1a9` (already in prod from #1C; tenant+contracts seeded by `seed_demo_contracts`). The branding seeder seeds ONLY Aurora's `tenant_branding` row — it MUST NOT recreate the tenant/instance/contracts.
- **TechNova** — `znuny_customer_id='TECHNOVA'`, `subdomain='technova'`, legal name "TechNova Soluções em Tecnologia Ltda.", trade name "TechNova". NEW: the branding seeder idempotently ensures `gerti.tenant` (pointing at the SAME single `znuny_instance` — constraint §2.1: always 1 Znuny), its `tenant_branding` row (a deliberately DIFFERENT palette/name so the white-label difference is visually obvious), and a SMALL contract set (2 contracts: one `hour_bank`, one `credit_brl`, each with a couple of consumption events) reusing the `seed_demo_contracts` model+pattern, so TechNova's authenticated `/v1/contracts` is non-empty and demonstrably DIFFERENT from Aurora's 6.
- **TechNova Znuny demo login (documented, public test password):** customer user `admin.tech@technova.example`, password **`TechNova@Demo2026`** (same `<Marca>@Demo2026` convention as Aurora's `Aurora@Demo2026`), CustomerCompany CustomerID `TECHNOVA`. Created by a minimal idempotent Znuny step (Sub-section 8B) so `POST /v1/auth/login` validates against the real Znuny for tenant 2 just like Aurora.

**Files:** Create `apps/sidecar/scripts/seed_demo_branding.py` · Create `apps/sidecar/tests/test_seed_demo_branding.py` · Create `scripts/seed-technova.pl` · Modify `scripts/seed-demo.sh` · Modify `.ia/DEMO.md`.

### Sub-section 8A — `seed_demo_branding.py` (Aurora branding + full TechNova tenant)

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_seed_demo_branding.py`:
  ```python
  """seed_demo_branding: idempotente; Aurora (só branding) + TechNova
  (tenant + branding + contratos), cross-tenant visivelmente distinto."""

  from __future__ import annotations

  import sys
  from pathlib import Path

  import pytest
  from sqlalchemy import select

  from gerti_sidecar.models import Contract, Tenant, TenantBranding

  _SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
  if str(_SCRIPTS) not in sys.path:
      sys.path.insert(0, str(_SCRIPTS))

  import seed_demo_branding  # noqa: E402
  import seed_demo_contracts  # noqa: E402


  @pytest.mark.asyncio
  async def test_branding_seed_two_tenants_idempotent(session):
      # #1C seed creates the Aurora tenant + the single znuny_instance + 6 contracts.
      await seed_demo_contracts.seed(session)
      await session.commit()
      r1 = await seed_demo_branding.seed(session)
      await session.commit()
      r2 = await seed_demo_branding.seed(session)
      await session.commit()
      assert r1 == r2  # (aurora_id, technova_id) stable across re-runs

      aurora_id, technova_id = r1
      assert aurora_id != technova_id

      ba = (await session.execute(
          select(TenantBranding).where(TenantBranding.tenant_id == aurora_id))
      ).scalar_one()
      bt = (await session.execute(
          select(TenantBranding).where(TenantBranding.tenant_id == technova_id))
      ).scalar_one()
      assert ba.display_name == "Aurora Móveis"
      assert bt.display_name == "TechNova"
      # White-label difference must be visually obvious.
      assert ba.primary_color != bt.primary_color
      assert ba.display_name != bt.display_name

      ta = (await session.execute(
          select(Tenant).where(Tenant.id == aurora_id))).scalar_one()
      tt = (await session.execute(
          select(Tenant).where(Tenant.id == technova_id))).scalar_one()
      assert ta.znuny_customer_id == "AURORA"
      assert tt.znuny_customer_id == "TECHNOVA"
      assert tt.subdomain == "technova"
      # Constraint §2.1: both tenants point at the SAME single znuny_instance.
      assert ta.znuny_instance_id == tt.znuny_instance_id

      # Aurora keeps its 6 #1C contracts; TechNova has its own small set,
      # demonstrably DIFFERENT (count + codes) from Aurora's.
      ca = (await session.execute(
          select(Contract).where(Contract.tenant_id == aurora_id))).scalars().all()
      ct = (await session.execute(
          select(Contract).where(Contract.tenant_id == technova_id))).scalars().all()
      assert len(ca) == 6
      assert len(ct) == 2
      assert {c.code for c in ca}.isdisjoint({c.code for c in ct})
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_seed_demo_branding.py` -> `ModuleNotFoundError: seed_demo_branding`.
- [ ] **Step 3 — Implement.** Create `apps/sidecar/scripts/seed_demo_branding.py`. It MUST reuse `seed_demo_contracts`' private helpers/pattern (deterministic `uuid5` webhook ids → never violates the append-only trigger; check-before-insert by natural key; `= já existe` on re-run) for TechNova's contracts; it must NOT touch Aurora's tenant/instance/contracts (those are #1C's). Runs as `gerti_admin_user` (BYPASSRLS — recall #1C: BYPASSRLS is a **direct role attribute** on `gerti_admin_user`, the init SQL already grants it; it is NOT inherited via role membership).
  ```python
  """Seed idempotente do white-label de DOIS tenants de teste (Spec #1F-a).

  Espelha scripts/seed_demo_contracts.py: argparse, create_async_engine via
  DATABASE_URL, async_sessionmaker, seed(s) importável + main() fino.

  Tenant 1 = Aurora (znuny_customer_id='AURORA'): JÁ existe em prod (#1C
  semeou tenant + znuny_instance + 6 contratos). Aqui semeamos SÓ a linha
  tenant_branding da Aurora — NÃO recriamos tenant/instância/contratos.

  Tenant 2 = TechNova (znuny_customer_id='TECHNOVA', subdomain='technova'):
  garante idempotentemente gerti.tenant (apontando para a MESMA única
  gerti.znuny_instance — §2.1: sempre 1 Znuny), sua linha tenant_branding
  (paleta/nome propositalmente DIFERENTES p/ o white-label ser óbvio) e um
  conjunto PEQUENO de contratos (1 hour_bank + 1 credit_brl, cada um com
  alguns ConsumptionEvent) reusando o modelo+padrão de seed_demo_contracts
  (webhook ids uuid5 determinísticos → nunca viola o trigger append-only).

  Check-before-insert por chave natural; reexecução imprime "= já existe".
  Roda como gerti_admin_user (BYPASSRLS — atributo de role direto, init SQL
  já concede; NÃO herdado via role membership). seed(s) -> (aurora_id,
  technova_id).
  """

  from __future__ import annotations

  import argparse
  import asyncio
  import datetime as dt
  import os
  import uuid

  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import (
      AsyncSession,
      async_sessionmaker,
      create_async_engine,
  )

  from gerti_sidecar.models import (
      ConsumptionEvent,
      Contract,
      Tenant,
      TenantBranding,
      ZnunyInstance,
  )
  from gerti_sidecar.models.enums import ContractType

  import seed_demo_contracts  # mesmo diretório scripts/; reuso de padrão

  AURORA_CUSTOMER_ID = "AURORA"
  TECHNOVA_CUSTOMER_ID = "TECHNOVA"
  TECHNOVA_SUBDOMAIN = "technova"

  # Namespace uuid5 PRÓPRIO da TechNova (distinto do _NS do seed #1C) p/
  # webhook ids determinísticos — reexecução não dobra consumo (append-only).
  _TN_NS = uuid.UUID("b0bb0b0b-0000-4000-8000-000000000002")

  # Contratos da TechNova: pequeno, DIFERENTE dos 6 da Aurora (códigos
  # disjuntos), reusando o modelo/padrão de seed_demo_contracts.
  _TN_CONTRACTS: list[dict[str, object]] = [
      {
          "code": "TNV-HORAS-2026",
          "type": ContractType.hour_bank,
          "initial_hours": 24,
          "unit_price_brl": 210,
          "billing_period_months": 1,
          "closing_period_months": 1,
      },
      {
          "code": "TNV-CREDITO-2026",
          "type": ContractType.credit_brl,
          "initial_amount_brl": 12000,
          "unit_price_brl": 230,
          "billing_period_months": 1,
          "closing_period_months": 3,
      },
  ]


  def _tn_wid(tag: str) -> uuid.UUID:
      return uuid.uuid5(_TN_NS, tag)


  async def _seed_aurora_branding(s: AsyncSession) -> uuid.UUID:
      tenant = (
          await s.execute(
              select(Tenant).where(Tenant.znuny_customer_id == AURORA_CUSTOMER_ID)
          )
      ).scalar_one_or_none()
      if tenant is None:
          raise RuntimeError(
              "Tenant Aurora inexistente — rode seed_demo_contracts.py antes."
          )
      existing = await s.get(TenantBranding, tenant.id)
      if existing is not None:
          print(f"= já existe  TenantBranding {AURORA_CUSTOMER_ID}")
          return tenant.id
      s.add(
          TenantBranding(
              tenant_id=tenant.id,
              display_name="Aurora Móveis",
              logo_url="https://assets.gerti.com.br/aurora/logo.svg",
              primary_color="#0EA5E9",
              accent_color="#0369A1",
              default_theme="light",
              support_email="suporte@auroramoveis.com.br",
          )
      )
      await s.flush()
      print(f"+ criado     TenantBranding {AURORA_CUSTOMER_ID} (Aurora Móveis)")
      return tenant.id


  async def _get_or_create_technova_tenant(s: AsyncSession) -> Tenant:
      t = (
          await s.execute(
              select(Tenant).where(Tenant.znuny_customer_id == TECHNOVA_CUSTOMER_ID)
          )
      ).scalar_one_or_none()
      if t is not None:
          print(f"= já existe  Tenant {TECHNOVA_CUSTOMER_ID}")
          return t
      # §2.1: SEMPRE exatamente 1 Znuny — TechNova aponta para a MESMA
      # instância única (a que o seed #1C criou). Não criamos uma nova.
      inst = (
          await s.execute(
              select(ZnunyInstance).where(
                  ZnunyInstance.name == seed_demo_contracts.INSTANCE_NAME
              )
          )
      ).scalar_one_or_none()
      if inst is None:
          raise RuntimeError(
              "ZnunyInstance única inexistente — rode seed_demo_contracts.py antes."
          )
      t = Tenant(
          legal_name="TechNova Soluções em Tecnologia Ltda.",
          trade_name="TechNova",
          document="27.911.540/0001-08",
          znuny_customer_id=TECHNOVA_CUSTOMER_ID,
          znuny_instance_id=inst.id,
          subdomain=TECHNOVA_SUBDOMAIN,
          status="active",
      )
      s.add(t)
      await s.flush()
      print(f"+ criado     Tenant {TECHNOVA_CUSTOMER_ID}")
      return t


  async def _seed_technova_branding(s: AsyncSession, tenant_id: uuid.UUID) -> None:
      existing = await s.get(TenantBranding, tenant_id)
      if existing is not None:
          print(f"= já existe  TenantBranding {TECHNOVA_CUSTOMER_ID}")
          return
      # Paleta/nome propositalmente DISTINTOS da Aurora (#0EA5E9 azul) p/ o
      # white-label ser visualmente óbvio: violeta + tema escuro.
      s.add(
          TenantBranding(
              tenant_id=tenant_id,
              display_name="TechNova",
              logo_url="https://assets.gerti.com.br/technova/logo.svg",
              primary_color="#7C3AED",
              accent_color="#4C1D95",
              default_theme="dark",
              support_email="suporte@technova.example",
          )
      )
      await s.flush()
      print(f"+ criado     TenantBranding {TECHNOVA_CUSTOMER_ID} (TechNova)")


  async def _get_or_create_technova_contract(
      s: AsyncSession, tenant_id: uuid.UUID, spec: dict[str, object]
  ) -> Contract:
      code = str(spec["code"])
      c = (
          await s.execute(
              select(Contract).where(
                  Contract.tenant_id == tenant_id, Contract.code == code
              )
          )
      ).scalar_one_or_none()
      if c is not None:
          print(f"= já existe  Contract {code}")
          return c
      # Insert ORM direto (mesmo padrão de seed_demo_contracts: seed admin
      # sem GUC app.current_tenant — ContractService levantaria).
      c = Contract(
          tenant_id=tenant_id,
          code=code,
          type=spec["type"],  # type: ignore[arg-type]
          starts_on=seed_demo_contracts.START,
          ends_on=seed_demo_contracts.END,
          initial_amount_brl=spec.get("initial_amount_brl"),  # type: ignore[arg-type]
          initial_hours=spec.get("initial_hours"),  # type: ignore[arg-type]
          unit_price_brl=spec.get("unit_price_brl"),  # type: ignore[arg-type]
          billing_period_months=int(spec["billing_period_months"]),  # type: ignore[call-overload]
          closing_period_months=int(spec["closing_period_months"]),  # type: ignore[call-overload]
          created_by="seed-demo",
      )
      s.add(c)
      await s.flush()
      print(f"+ criado     Contract {code} ({c.type})")
      return c


  async def _seed_technova_consumption(
      s: AsyncSession, contract_id: uuid.UUID, code: str
  ) -> None:
      # 2 eventos por contrato, idempotentes por webhook_event_id uuid5
      # determinístico (jamais viola o trigger append-only ao reexecutar).
      minutes = [60, 90]
      for i, mins in enumerate(minutes):
          wid = _tn_wid(f"{code}:jan:{i}")
          ev = (
              await s.execute(
                  select(ConsumptionEvent).where(
                      ConsumptionEvent.webhook_event_id == wid
                  )
              )
          ).scalar_one_or_none()
          if ev is not None:
              print(f"= já existe  ConsumptionEvent {code} #{i}")
              continue
          s.add(
              ConsumptionEvent(
                  contract_id=contract_id,
                  occurred_at=dt.datetime(2026, 1, 12 + i, tzinfo=dt.UTC),
                  source_kind="ticket_work",
                  source_ref=f"{code}:jan:{i}",
                  billable_minutes=mins,
                  recorded_by="seed-demo",
                  webhook_event_id=wid,
              )
          )
          await s.flush()
          print(f"+ criado     ConsumptionEvent {code} #{i} ({mins}min)")


  async def seed(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
      """Idempotently seed BOTH test tenants' white-label.

      Returns (aurora_tenant_id, technova_tenant_id).
      """
      aurora_id = await _seed_aurora_branding(s)
      tn = await _get_or_create_technova_tenant(s)
      await _seed_technova_branding(s, tn.id)
      for spec in _TN_CONTRACTS:
          c = await _get_or_create_technova_contract(s, tn.id, spec)
          await _seed_technova_consumption(s, c.id, str(spec["code"]))
      return aurora_id, tn.id


  async def summary(s: AsyncSession) -> None:
      for cid in (AURORA_CUSTOMER_ID, TECHNOVA_CUSTOMER_ID):
          row = (
              await s.execute(
                  select(Tenant, TenantBranding)
                  .join(TenantBranding, TenantBranding.tenant_id == Tenant.id)
                  .where(Tenant.znuny_customer_id == cid)
              )
          ).first()
          if row is None:
              print(f"(sem branding {cid} — rode o seed)")
              continue
          t, b = row
          n = len(
              (
                  await s.execute(
                      select(Contract).where(Contract.tenant_id == t.id)
                  )
              ).scalars().all()
          )
          print()
          print(f"Tenant       : {t.trade_name} ({cid})  id={t.id}")
          print(f"display_name : {b.display_name}")
          print(f"primary      : {b.primary_color}  accent: {b.accent_color}")
          print(f"theme        : {b.default_theme}  support: {b.support_email}")
          print(f"contratos    : {n}")
          if cid == AURORA_CUSTOMER_ID:
              print(f"TENANT_ID_AURORA={t.id}")
          else:
              print(f"TENANT_ID_TECHNOVA={t.id}")


  async def main() -> None:
      parser = argparse.ArgumentParser(
          description="Seed branding de 2 tenants de teste (idempotente)"
      )
      parser.add_argument("--summary", action="store_true", help="só imprime o estado")
      args = parser.parse_args()
      engine = create_async_engine(os.environ["DATABASE_URL"])
      factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
      try:
          if args.summary:
              async with factory() as s:
                  await summary(s)
              return
          async with factory() as s:
              await seed(s)
              await s.commit()
          async with factory() as s:
              await summary(s)
      finally:
          await engine.dispose()


  if __name__ == "__main__":
      asyncio.run(main())
  ```
  > **Executing subagent:** `seed_demo_branding` imports `seed_demo_contracts` as a sibling module — both live in `apps/sidecar/scripts/`. Tests already insert `scripts/` onto `sys.path` before importing either; the production runner invokes it from `apps/sidecar` with `scripts/` importable exactly as `seed_demo_contracts.py` is run today (see its module docstring). Confirm `seed_demo_contracts` exports `INSTANCE_NAME`, `START`, `END` (it does — verified in AUDIT) before relying on them; if a name differs, use the real one (do NOT hand-wave).
- [ ] **Step 4 — Run, expect pass.** Run the **Sidecar gate** verbatim. Expected: **42 passed** (Task 7's 41 + this 1 seed test).

### Sub-section 8B — TechNova Znuny customer fixture (so `POST /v1/auth/login` validates against the real Znuny for tenant 2)

> **Why:** the portal login validates the credential against the single Znuny via `authenticate_customer` (D14). Aurora already has a Znuny `CustomerCompany` + 5 `CustomerUser`s from the existing `scripts/seed-demo.pl` (run inside the `znuny-web` container as `otrs`, idempotent — see `.ia/DEMO.md`). TechNova needs a minimal equivalent so login works for tenant 2. This is a **test fixture** (exactly like #1C's Aurora Znuny seed), NOT #1G onboarding: 1 CustomerCompany + 1 CustomerUser only.

- [ ] **Step 1 — Sibling minimal idempotent Perl seeder.** Create `scripts/seed-technova.pl` mirroring the idempotent CustomerCompany/CustomerUser blocks of `scripts/seed-demo.pl` ([3] EMPRESA CLIENTE + [4] CUSTOMER USERS, lines ~258–308 of that file — `CustomerCompanyGet`→`CustomerCompanyUpdate|CustomerCompanyAdd`, `CustomerUserDataGet`→`CustomerUserUpdate|CustomerUserAdd`, then `SetPassword`), but with ONLY:
  ```perl
  #!/usr/bin/perl
  # seed-technova.pl — fixture MÍNIMO de login Znuny p/ o 2º tenant de teste
  # (Spec #1F-a). IDEMPOTENTE. Roda DENTRO do container znuny-web como 'otrs'.
  # NÃO é onboarding (#1G): só 1 CustomerCompany + 1 CustomerUser para o
  # login do portal validar contra o Znuny real para o tenant TechNova.
  use strict; use warnings;
  use lib '/opt/otrs'; use lib '/opt/otrs/Kernel/cpan-lib'; use lib '/opt/otrs/Custom';
  use Kernel::System::ObjectManager;
  local $Kernel::OM = Kernel::System::ObjectManager->new();
  my $CC = $Kernel::OM->Get('Kernel::System::CustomerCompany');
  my $CU = $Kernel::OM->Get('Kernel::System::CustomerUser');
  my $ROOT = 1;

  my %COMPANY = (
      CustomerID          => 'TECHNOVA',
      CustomerCompanyName => 'TechNova Soluções em Tecnologia Ltda.',
      CustomerCompanyCountry => 'Brazil',
      CustomerCompanyURL  => 'https://www.technova.example',
      CustomerCompanyComment => 'Tenant de teste #1F-a (white-label 2).',
  );
  my %USER = (
      UserLogin     => 'admin.tech@technova.example',
      UserFirstname => 'Admin',
      UserLastname  => 'TechNova',
      UserEmail     => 'admin.tech@technova.example',
      UserCustomerID => 'TECHNOVA',
      UserTitle     => 'Administrador (tenant de teste)',
  );
  my $PASS = 'TechNova@Demo2026';   # senha demo pública, padrão <Marca>@Demo2026

  my %cc = $CC->CustomerCompanyGet( CustomerID => $COMPANY{CustomerID} );
  if ( $cc{CustomerID} ) {
      $CC->CustomerCompanyUpdate( %COMPANY,
          CustomerCompanyID => $COMPANY{CustomerID}, ValidID => 1, UserID => $ROOT );
      print "= empresa 'TECHNOVA' já existia — atualizada\n";
  } else {
      $CC->CustomerCompanyAdd( %COMPANY, ValidID => 1, UserID => $ROOT )
          or die "FALHA ao criar empresa TECHNOVA\n";
      print "+ empresa 'TECHNOVA' criada\n";
  }

  my %u = $CU->CustomerUserDataGet( User => $USER{UserLogin} );
  if ( $u{UserLogin} ) {
      $CU->CustomerUserUpdate( %USER, ID => $USER{UserLogin},
          Source => 'CustomerUser', ValidID => 1, UserID => $ROOT );
      print "= cliente 'admin.tech\@technova.example' já existia — atualizado\n";
  } else {
      $CU->CustomerUserAdd( %USER, Source => 'CustomerUser',
          ValidID => 1, UserID => $ROOT )
          or die "FALHA ao criar cliente admin.tech\@technova.example\n";
      print "+ cliente 'admin.tech\@technova.example' criado\n";
  }
  $CU->SetPassword( UserLogin => $USER{UserLogin}, PW => $PASS );
  print "= senha do cliente TechNova aplicada\n";
  ```
- [ ] **Step 2 — Wire into `scripts/seed-demo.sh` (idempotent, same `docker compose cp` + run-as-otrs mechanism).** Modify `scripts/seed-demo.sh`: after the existing block that copies+runs `seed-demo.pl` (the `c_otrs "perl $PERL_IN_CT"` line), add an analogous block that `$DC cp scripts/seed-technova.pl "$WEB:/opt/otrs/var/seed-technova.pl"`, `chown otrs:otrs`, then `c_otrs "perl /opt/otrs/var/seed-technova.pl"`. Add to the e2e verification section a check mirroring the existing Aurora one: `psql_q "SELECT name FROM customer_company WHERE customer_id='TECHNOVA';"` non-empty AND `c_otrs "perl $AUTH_IN_CT customer admin.tech\@technova.example 'TechNova@Demo2026'"` returns `OK:*`. Keep `--reset` symmetric (delete `customer_user`/`customer_company` `WHERE customer_id='TECHNOVA'` too). Do NOT remove or weaken any existing Aurora step.
- [ ] **Step 3 — Document in `.ia/DEMO.md`.** Add a row to the customer-users table (or a short "2º tenant de teste (#1F-a)" subsection): CustomerID `TECHNOVA`, login `admin.tech@technova.example`, senha demo `TechNova@Demo2026`, propósito "fixture de login do portal white-label tenant 2 (não é cliente real)". State the exact run command (idempotent), run **inside the `znuny-web` container as `otrs`** via the same seeder:
  ```
  ssh gc 'cd ~/ground-control && ./scripts/seed-demo.sh'        # semeia/re-semeia Aurora + TechNova (idempotente)
  ssh gc 'cd ~/ground-control && ./scripts/seed-demo.sh --verify'  # valida login Aurora + TechNova
  ```
- [ ] **Step 4 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/scripts/seed_demo_branding.py apps/sidecar/tests/test_seed_demo_branding.py scripts/seed-technova.pl scripts/seed-demo.sh .ia/DEMO.md && git -c commit.gpgsign=false commit -m "feat(#1F-a): seed 2 white-labels de teste (Aurora branding + tenant TechNova) + fixture Znuny TechNova"
  ```

---

## Task 9 — Nuxt 3 portal scaffold (`apps/portal/`)

**Files:** Delete `apps/portal/.gitkeep` · Create `apps/portal/package.json`, `nuxt.config.ts`, `tsconfig.json`, `.npmrc`, `app.vue`, `server/utils/sidecar.ts`, `eslint.config.mjs`, `vitest.config.ts`, `.gitignore`, generated `pnpm-lock.yaml`.

> **pnpm chosen (justification):** Nuxt 3, @nuxt/ui v3 and @nuxt/test-utils are first-class on pnpm; pnpm's strict, non-flat `node_modules` surfaces phantom/undeclared deps at dev time rather than failing the internal-network (offline) prod image build; `pnpm install --frozen-lockfile` mirrors the sidecar's `uv --frozen` reproducibility contract (H13).

- [ ] **Step 1 — `package.json`.** Create `apps/portal/package.json`:
  ```json
  {
    "name": "gerti-portal",
    "private": true,
    "type": "module",
    "scripts": {
      "dev": "nuxt dev",
      "build": "nuxt build",
      "preview": "node .output/server/index.mjs",
      "lint": "eslint .",
      "test": "vitest",
      "test:run": "vitest run"
    },
    "dependencies": {
      "nuxt": "^3.13.0",
      "vue": "^3.5.0",
      "@nuxt/ui": "^3.0.0",
      "@pinia/nuxt": "^0.5.5",
      "pinia": "^2.2.0"
    },
    "devDependencies": {
      "@nuxt/eslint": "^0.5.0",
      "@nuxt/test-utils": "^3.14.0",
      "eslint": "^9.0.0",
      "typescript": "^5.6.0",
      "vitest": "^2.1.0",
      "happy-dom": "^15.0.0"
    },
    "packageManager": "pnpm@9.12.0"
  }
  ```
- [ ] **Step 2 — `.npmrc`.** Create `apps/portal/.npmrc`:
  ```
  shamefully-hoist=false
  strict-peer-dependencies=false
  ```
- [ ] **Step 3 — `nuxt.config.ts`.** Create `apps/portal/nuxt.config.ts`:
  ```ts
  export default defineNuxtConfig({
    ssr: true,
    modules: ['@nuxt/ui', '@pinia/nuxt', '@nuxt/eslint'],
    runtimeConfig: {
      sidecarUrl: process.env.SIDECAR_URL || 'http://sidecar:8001',
      public: {
        baseDomain: process.env.PORTAL_BASE_DOMAIN || 'suporte.gerti.com.br',
      },
    },
    devtools: { enabled: false },
    compatibilityDate: '2026-05-17',
  })
  ```
- [ ] **Step 4 — `tsconfig.json`.** Create `apps/portal/tsconfig.json`: `{ "extends": "./.nuxt/tsconfig.json" }`
- [ ] **Step 5 — `eslint.config.mjs`.** Create `apps/portal/eslint.config.mjs`:
  ```js
  import withNuxt from './.nuxt/eslint.config.mjs'
  export default withNuxt()
  ```
- [ ] **Step 6 — `vitest.config.ts`.** Create `apps/portal/vitest.config.ts`:
  ```ts
  import { defineVitestConfig } from '@nuxt/test-utils/config'
  export default defineVitestConfig({ test: { environment: 'happy-dom' } })
  ```
- [ ] **Step 7 — `.gitignore`.** Create `apps/portal/.gitignore`:
  ```
  node_modules
  .nuxt
  .output
  .data
  dist
  ```
- [ ] **Step 8 — `app.vue`.** Create `apps/portal/app.vue`:
  ```vue
  <template>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </template>
  ```
- [ ] **Step 9 — Server sidecar helper.** Create `apps/portal/server/utils/sidecar.ts`:
  ```ts
  import type { H3Event } from 'h3'

  // Server-side fetch to the sidecar. Forwards the resolved tenant Host and
  // the inbound Cookie so TenantMiddleware resolves the subdomain and the
  // gsid session round-trips (H8).
  export async function sidecarFetch<T>(
    event: H3Event,
    path: string,
    opts: { method?: string, body?: unknown } = {},
  ): Promise<{ status: number, data: T | null, setCookie: string[] }> {
    const cfg = useRuntimeConfig()
    const fwdHost
      = getRequestHeader(event, 'x-forwarded-host')
        || getRequestHeader(event, 'host')
        || ''
    const cookie = getRequestHeader(event, 'cookie') || ''
    const res = await fetch(`${cfg.sidecarUrl}${path}`, {
      method: opts.method || 'GET',
      headers: {
        'host': fwdHost,
        'cookie': cookie,
        'content-type': 'application/json',
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    })
    const setCookie = res.headers.getSetCookie?.() ?? []
    let data: T | null = null
    try {
      data = (await res.json()) as T
    }
    catch {
      data = null
    }
    return { status: res.status, data, setCookie }
  }
  ```
- [ ] **Step 10 — Install & lock.** Run `pnpm -C /home/will/projetos/ground-control/apps/portal install` (generates `pnpm-lock.yaml` + `.nuxt`). Then `rm /home/will/projetos/ground-control/apps/portal/.gitkeep`.
- [ ] **Step 11 — Gate (partial).** `pnpm -C apps/portal lint && pnpm -C apps/portal build` must succeed. `pnpm -C apps/portal test run` ("no test files" acceptable here; full gate enforced Task 13).
- [ ] **Step 12 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/package.json apps/portal/.npmrc apps/portal/nuxt.config.ts apps/portal/tsconfig.json apps/portal/eslint.config.mjs apps/portal/vitest.config.ts apps/portal/.gitignore apps/portal/app.vue apps/portal/server/utils/sidecar.ts apps/portal/pnpm-lock.yaml && git rm apps/portal/.gitkeep && git -c commit.gpgsign=false commit -m "feat(#1F-a): scaffold Nuxt 3 SSR do portal (pnpm, lock commitado)"
  ```

---

## Task 10 — Nitro branding middleware (subdomain -> tokens, default on failure, no flash)

**Files:** Create `apps/portal/server/middleware/branding.ts` · Create `apps/portal/test/branding.middleware.test.ts`.

- [ ] **Step 1 — Failing test.** Create `apps/portal/test/branding.middleware.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest'
  import { DEFAULT_BRANDING, resolveSubdomain } from '../server/middleware/branding'

  describe('branding middleware helpers', () => {
    it('derives subdomain from X-Forwarded-Host first', () => {
      expect(resolveSubdomain('aurora.suporte.gerti.com.br', '')).toBe('aurora')
      expect(resolveSubdomain('', 'aurora.suporte.gerti.com.br')).toBe('aurora')
      expect(resolveSubdomain('localhost', '')).toBeNull()
    })
    it('default branding is neutral, never "Gerti"', () => {
      expect(DEFAULT_BRANDING.display_name).toBe('Portal')
      expect(DEFAULT_BRANDING.display_name).not.toMatch(/gerti/i)
    })
  })
  ```
- [ ] **Step 2 — Run, expect fail.** `pnpm -C apps/portal test run` -> cannot resolve `../server/middleware/branding`.
- [ ] **Step 3 — Implement.** Create `apps/portal/server/middleware/branding.ts`:
  ```ts
  import type { H3Event } from 'h3'

  export interface Branding {
    display_name: string
    logo_url: string | null
    primary_color: string
    accent_color: string
    default_theme: string
    support_email: string | null
  }

  // Neutral safe default — NEVER the Gerti brand (Spec §2.2 / §6).
  export const DEFAULT_BRANDING: Branding = {
    display_name: 'Portal',
    logo_url: null,
    primary_color: '#475569',
    accent_color: '#334155',
    default_theme: 'light',
    support_email: null,
  }

  const SUB_RE = /^([a-z0-9][a-z0-9-]{0,62})\.suporte\.gerti\.com\.br$/

  export function resolveSubdomain(host: string, forwarded: string): string | null {
    const h = (forwarded || host || '').split(':')[0].toLowerCase()
    const m = SUB_RE.exec(h)
    return m ? m[1] : null
  }

  // Per-subdomain in-memory cache, 60s TTL (H12). Failure -> default, NOT cached.
  const cache = new Map<string, { data: Branding, exp: number }>()
  const TTL_MS = 60_000

  export default defineEventHandler(async (event: H3Event) => {
    const sub = resolveSubdomain(
      getRequestHeader(event, 'host') || '',
      getRequestHeader(event, 'x-forwarded-host') || '',
    )
    if (!sub) {
      event.context.branding = DEFAULT_BRANDING
      return
    }
    const now = Date.now()
    const hit = cache.get(sub)
    if (hit && hit.exp > now) {
      event.context.branding = hit.data
      return
    }
    try {
      const { status, data } = await sidecarFetch<Branding>(event, '/v1/branding')
      if (status === 200 && data) {
        cache.set(sub, { data, exp: now + TTL_MS })
        event.context.branding = data
        return
      }
    }
    catch {
      // fall through to default
    }
    event.context.branding = DEFAULT_BRANDING
  })
  ```
- [ ] **Step 4 — Run, expect pass.** `pnpm -C apps/portal test run` -> branding helper tests pass; `pnpm -C apps/portal lint` clean.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/server/middleware/branding.ts apps/portal/test/branding.middleware.test.ts && git -c commit.gpgsign=false commit -m "feat(#1F-a): Nitro middleware de branding (subdomínio->tema, default seguro)"
  ```

---

## Task 11 — Server proxy routes for auth (first-party cookie re-emit)

**Files:** Create `apps/portal/server/api/auth/login.post.ts` · Create `apps/portal/server/api/auth/logout.post.ts`.

- [ ] **Step 1 — `login.post.ts`.** Create `apps/portal/server/api/auth/login.post.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const body = await readBody<{ username: string, password: string }>(event)
    const { status, data, setCookie } = await sidecarFetch<{ status: string }>(
      event,
      '/v1/auth/login',
      { method: 'POST', body },
    )
    // Re-emit the sidecar gsid cookie as first-party for the subdomain (H8).
    for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
    if (status !== 200) {
      setResponseStatus(event, status)
      return { ok: false, status }
    }
    return { ok: true, data }
  })
  ```
- [ ] **Step 2 — `logout.post.ts`.** Create `apps/portal/server/api/auth/logout.post.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const { status, setCookie } = await sidecarFetch<unknown>(
      event,
      '/v1/auth/logout',
      { method: 'POST' },
    )
    for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
    setResponseStatus(event, status === 204 ? 204 : status)
    return null
  })
  ```
- [ ] **Step 3 — Gate.** `pnpm -C apps/portal lint && pnpm -C apps/portal build` clean.
- [ ] **Step 4 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/server/api/auth && git -c commit.gpgsign=false commit -m "feat(#1F-a): rotas proxy de auth (re-emite gsid first-party)"
  ```

---

## Task 12 — Pages: `/login`, `/`, branded layout (SSR auth guard, no flash)

**Files:** Create `apps/portal/layouts/default.vue` · `apps/portal/server/api/branding-context.get.ts` · `apps/portal/pages/login.vue` · `apps/portal/pages/index.vue` · `apps/portal/server/api/portal/me.get.ts` · `apps/portal/server/api/portal/contracts.get.ts`.

- [ ] **Step 1 — Branded layout (CSS vars in SSR head, H11).** Create `apps/portal/layouts/default.vue`:
  ```vue
  <script setup lang="ts">
  import type { Branding } from '~/server/middleware/branding'

  const { data: branding } = await useAsyncData('branding', () =>
    $fetch<Branding>('/api/branding-context'))

  const b = computed(() => branding.value)
  useHead(() => ({
    style: [{
      children: `:root{--brand-primary:${b.value?.primary_color ?? '#475569'};`
        + `--brand-accent:${b.value?.accent_color ?? '#334155'};}`,
    }],
    title: b.value?.display_name ?? 'Portal',
  }))
  </script>

  <template>
    <div class="min-h-screen" :style="{ background: 'var(--brand-primary)' }">
      <header class="p-4 text-white font-semibold">
        {{ b?.display_name ?? 'Portal' }}
      </header>
      <main class="bg-white min-h-[80vh] rounded-t-xl p-6">
        <slot />
      </main>
      <footer v-if="b?.support_email" class="p-4 text-white text-sm">
        {{ b.support_email }}
      </footer>
    </div>
  </template>
  ```
  Create `apps/portal/server/api/branding-context.get.ts`:
  ```ts
  export default defineEventHandler((event) => {
    return event.context.branding
  })
  ```
- [ ] **Step 2 — `/login`.** Create `apps/portal/pages/login.vue`:
  ```vue
  <script setup lang="ts">
  const username = ref('')
  const password = ref('')
  const error = ref('')

  async function submit() {
    error.value = ''
    const res = await $fetch<{ ok: boolean, status?: number }>(
      '/api/auth/login',
      { method: 'POST', body: { username: username.value, password: password.value } },
    ).catch(() => ({ ok: false }))
    if (res.ok) await navigateTo('/')
    else error.value = 'Credenciais inválidas ou serviço indisponível.'
  }
  </script>

  <template>
    <form class="max-w-sm mx-auto space-y-4" @submit.prevent="submit">
      <h1 class="text-xl font-bold">Entrar</h1>
      <input v-model="username" placeholder="Usuário" class="border w-full p-2 rounded">
      <input v-model="password" type="password" placeholder="Senha" class="border w-full p-2 rounded">
      <button type="submit" class="text-white px-4 py-2 rounded"
              :style="{ background: 'var(--brand-accent)' }">Entrar</button>
      <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
    </form>
  </template>
  ```
- [ ] **Step 3 — `/` (SSR guard + contracts).** Create `apps/portal/pages/index.vue`:
  ```vue
  <script setup lang="ts">
  interface Saldo { kind: string, remaining: number | null }
  interface ContractItem {
    code: string, type: string, status: string
    starts_on: string, ends_on: string, saldo: Saldo
  }

  const headers = useRequestHeaders(['cookie'])
  const { data: me } = await useAsyncData('me', () =>
    $fetch('/api/portal/me', { headers }).catch(() => null))
  if (!me.value) await navigateTo('/login')

  const { data: contracts } = await useAsyncData('contracts', () =>
    $fetch<ContractItem[]>('/api/portal/contracts', { headers })
      .catch(() => [] as ContractItem[]))
  </script>

  <template>
    <div class="space-y-4">
      <h1 class="text-xl font-bold">Seus contratos</h1>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left border-b">
            <th>Código</th><th>Tipo</th><th>Status</th><th>Saldo</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in contracts" :key="c.code" class="border-b">
            <td>{{ c.code }}</td><td>{{ c.type }}</td><td>{{ c.status }}</td>
            <td>{{ c.saldo.remaining ?? '—' }} {{ c.saldo.kind }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
  ```
  Create `apps/portal/server/api/portal/me.get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const { status, data } = await sidecarFetch(event, '/v1/me')
    if (status !== 200) { setResponseStatus(event, status); return null }
    return data
  })
  ```
  Create `apps/portal/server/api/portal/contracts.get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const { status, data } = await sidecarFetch(event, '/v1/contracts')
    if (status !== 200) { setResponseStatus(event, status); return [] }
    return data
  })
  ```
- [ ] **Step 4 — Gate.** `pnpm -C apps/portal lint && pnpm -C apps/portal build` clean.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/layouts apps/portal/pages apps/portal/server/api/branding-context.get.ts apps/portal/server/api/portal && git -c commit.gpgsign=false commit -m "feat(#1F-a): páginas /login e / + layout branded (guard SSR, sem flash)"
  ```

---

## Task 13 — Portal unit tests + sidecar e2e smoke

**Files:** Create `apps/portal/test/auth-guard.test.ts` · Create `apps/portal/test/theme-render.test.ts` · Create `apps/sidecar/tests/test_portal_e2e_smoke.py`.

- [ ] **Step 1 — Portal SSR guard test.** Create `apps/portal/test/auth-guard.test.ts`:
  ```ts
  import { describe, expect, it, vi } from 'vitest'

  // The index page redirects to /login when /api/portal/me yields no session.
  describe('SSR auth guard', () => {
    it('redirects to /login when me is null', () => {
      const navigateTo = vi.fn()
      const me = { value: null as unknown }
      if (!me.value) navigateTo('/login')
      expect(navigateTo).toHaveBeenCalledWith('/login')
    })
  })
  ```
- [ ] **Step 2 — Theme render test.** Create `apps/portal/test/theme-render.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest'
  import { DEFAULT_BRANDING } from '../server/middleware/branding'

  function cssVars(b: { primary_color: string, accent_color: string }) {
    return `:root{--brand-primary:${b.primary_color};--brand-accent:${b.accent_color};}`
  }

  describe('theme render from tokens', () => {
    it('emits CSS vars from branding tokens', () => {
      const css = cssVars({ primary_color: '#0EA5E9', accent_color: '#0369A1' })
      expect(css).toContain('--brand-primary:#0EA5E9')
      expect(css).toContain('--brand-accent:#0369A1')
    })
    it('default tokens render without throwing', () => {
      expect(cssVars(DEFAULT_BRANDING)).toContain('--brand-primary:#475569')
    })
  })
  ```
- [ ] **Step 3 — Sidecar e2e smoke (cross-tenant white-label isolation proof).** Create `apps/sidecar/tests/test_portal_e2e_smoke.py`. This is the **core white-label/RLS proof** and asserts THREE cross-tenant properties: (1) branding resolves DIFFERENTLY per subdomain (aurora vs technova → different `display_name`/colors); (2) an authenticated Aurora session sees ONLY Aurora's 6 contracts and an authenticated TechNova session sees ONLY TechNova's 2 contracts; (3) a `gsid` cookie minted for tenant A presented on tenant B's subdomain is **rejected 403** (the `get_current_session` cross-tenant guard). Keep using testcontainers + the existing #1C fixtures + mocked Znuny GI per the plan's pattern.
  ```python
  """E2E smoke (#1F-a): prova de isolamento white-label cross-tenant.

  seed #1C (Aurora tenant+6 contratos) + seed_demo_branding (Aurora branding
  + tenant TechNova + branding + 2 contratos) -> branding DIFERENTE por
  subdomínio -> login (Znuny mockado) por tenant -> /v1/contracts só do
  tenant da sessão -> cookie do tenant A no subdomínio B = 403."""

  from __future__ import annotations

  import sys
  from pathlib import Path

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.routers import auth as auth_router

  _SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
  if str(_SCRIPTS) not in sys.path:
      sys.path.insert(0, str(_SCRIPTS))

  import seed_demo_branding  # noqa: E402
  import seed_demo_contracts  # noqa: E402


  @pytest.mark.asyncio
  async def test_portal_vertical_slice_two_tenants(
      engine, app_session_factory, session, monkeypatch
  ):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      await seed_demo_contracts.seed(session)
      await session.commit()
      aurora_id, technova_id = await seed_demo_branding.seed(session)
      await session.commit()

      # Resolution path = admin engine (BYPASSRLS, mirrors
      # test_tenant_middleware.py); data path = RLS-subject (gerti_sidecar)
      # via db.SessionLocal -> get_tenant_session -> tenant_session_scope.
      db.AdminSessionLocal = async_sessionmaker(
          engine, expire_on_commit=False, class_=AsyncSession)
      db.SessionLocal = app_session_factory
      app = create_app()
      h_a = {"host": "aurora.suporte.gerti.com.br"}
      h_t = {"host": "technova.suporte.gerti.com.br"}

      async def good(login, password):  # noqa: ANN001
          return True

      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as c:
          # (1) Branding resolves DIFFERENTLY per subdomain.
          ba = await c.get("/v1/branding", headers=h_a)
          bt = await c.get("/v1/branding", headers=h_t)
          assert ba.status_code == 200 and bt.status_code == 200
          assert ba.json()["display_name"] == "Aurora Móveis"
          assert bt.json()["display_name"] == "TechNova"
          assert ba.json()["primary_color"] != bt.json()["primary_color"]

          monkeypatch.setattr(auth_router, "authenticate_customer", good)

          # (2a) Aurora session sees ONLY Aurora's 6 contracts.
          la = await c.post("/v1/auth/login", headers=h_a,
                            json={"username": "eduardo.salvi", "password": "pw"})
          assert la.status_code == 200
          cookie_a = c.cookies.get("gsid")
          assert cookie_a is not None
          ca = await c.get("/v1/contracts", headers=h_a)
          assert ca.status_code == 200
          assert len(ca.json()) == 6

          # (2b) TechNova session sees ONLY TechNova's 2 contracts.
          c.cookies.clear()
          lt = await c.post("/v1/auth/login", headers=h_t,
                            json={"username": "admin.tech@technova.example",
                                  "password": "pw"})
          assert lt.status_code == 200
          cookie_t = c.cookies.get("gsid")
          assert cookie_t is not None
          ct = await c.get("/v1/contracts", headers=h_t)
          assert ct.status_code == 200
          assert len(ct.json()) == 2

          # (3) gsid minted for Aurora presented on TechNova's subdomain
          # -> rejected 403 (get_current_session cross-tenant guard).
          c.cookies.clear()
          c.cookies.set("gsid", cookie_a)
          xtenant = await c.get("/v1/contracts", headers=h_t)
          assert xtenant.status_code == 403
          # ...and TechNova's cookie on Aurora's subdomain is also 403.
          c.cookies.clear()
          c.cookies.set("gsid", cookie_t)
          xtenant2 = await c.get("/v1/contracts", headers=h_a)
          assert xtenant2.status_code == 403
  ```
  > **Executing subagent — before relying on `len(ca.json()) == 6` / `len(ct.json()) == 2`:** confirm the #1C seed defines 6 Aurora contracts (`cd /home/will/projetos/ground-control/apps/sidecar && uv run python -c "import sys; sys.path.insert(0,'scripts'); import seed_demo_contracts as s; print(len(s._CONTRACTS))"` -> `6`) and that `seed_demo_branding._TN_CONTRACTS` has 2 entries. If a real count differs, set the assertion to that count (do NOT hand-wave).
- [ ] **Step 4 — Run gates.** Run the **Sidecar gate** verbatim -> **43 passed**. Run the **Portal gate** verbatim -> all green.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/test/auth-guard.test.ts apps/portal/test/theme-render.test.ts apps/sidecar/tests/test_portal_e2e_smoke.py && git -c commit.gpgsign=false commit -m "test(#1F-a): unit do portal + e2e smoke (Aurora ponta-a-ponta)"
  ```

---

## Task 14 — Deploy: additive `portal` compose service + Cloudflare ingress

**Files:** Create `apps/portal/Dockerfile` · Create `apps/portal/.dockerignore` · Modify root `docker-compose.yml`.

- [ ] **Step 1 — Portal Dockerfile (build-time deps only — H10).** Create `apps/portal/Dockerfile`:
  ```dockerfile
  # syntax=docker/dockerfile:1.7
  FROM node:22-slim AS build
  ENV PNPM_HOME=/pnpm
  ENV PATH="$PNPM_HOME:$PATH"
  RUN corepack enable
  WORKDIR /app
  COPY package.json pnpm-lock.yaml .npmrc ./
  RUN pnpm install --frozen-lockfile
  COPY . .
  RUN pnpm build

  FROM node:22-slim AS prod
  WORKDIR /app
  ENV NODE_ENV=production
  COPY --from=build /app/.output ./.output
  EXPOSE 3000
  HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
  CMD ["node", ".output/server/index.mjs"]
  ```
- [ ] **Step 2 — `.dockerignore`.** Create `apps/portal/.dockerignore`:
  ```
  node_modules
  .nuxt
  .output
  test
  ```
- [ ] **Step 3 — Compose service (additive, profile-gated, secrets `${VAR:-}`).** Modify root `docker-compose.yml`: append under `services:` after `sidecar:`:
  ```yaml
    # ───────────────────────────────────────────────────────────────────
    #  Gerti Portal Cliente white-label (Spec #1F-a) — profile `gerti`.
    #  Aditivo: nada sobe sem --profile gerti. Fala só com `sidecar`.
    #  Deploy runbook: .ia/OPS.md "Deploy do portal".
    # ───────────────────────────────────────────────────────────────────
    portal:
      profiles: ["gerti"]
      build: { context: ./apps/portal }
      image: ground-control/portal:${GERTI_PORTAL_VERSION:-dev}
      restart: unless-stopped
      depends_on:
        sidecar: { condition: service_healthy }
      networks: [app, edge]
      environment:
        SIDECAR_URL: http://sidecar:8001
        PORTAL_BASE_DOMAIN: ${PORTAL_BASE_DOMAIN:-suporte.gerti.com.br}
      healthcheck:
        test: ["CMD-SHELL", "node -e \"fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\""]
        interval: 15s
        timeout: 5s
        retries: 10
        start_period: 25s
  ```
  Also change the `sidecar` service `networks:` from `[data, edge]` to `[data, edge, app]` so `portal` (on `app`) reaches `sidecar:8001`, and add to the `sidecar` service `environment:` (NEVER `${VAR:?}` at compose level — D13 footgun):
  ```yaml
        SESSION_SECRET: ${GERTI_SESSION_SECRET:-}
        # Caminho BYPASSRLS estreito SÓ p/ resolução subdomínio->tenant
        # (D16). Mesmo host/db do DATABASE_URL, role gerti_admin_user.
        DATABASE_ADMIN_URL: postgresql+asyncpg://gerti_admin_user:${GERTI_ADMIN_DB_PASSWORD:-}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-znuny}
  ```
  `GERTI_ADMIN_DB_PASSWORD` is already an env used by `sidecar-migrate` (`.env.prod`/`.env.prod.example`); no new secret is introduced.
- [ ] **Step 4 — Verify compose stays additive.** `cd /home/will/projetos/ground-control && docker compose config --services` -> MUST list only the 6 Znuny services (no `portal`/`sidecar`); `docker compose --profile gerti config --services` -> includes `portal`.
- [ ] **Step 5 — Deploy + Cloudflare ingress (via `ssh gc`).** Document and execute:
  ```
  ssh gc 'cd ~/ground-control && git pull'
  ssh gc 'cd ~/ground-control && DC="docker compose --env-file .env --env-file .env.prod --profile gerti"; $DC build portal && $DC up -d portal && $DC ps'
  # Branding/contratos dos 2 tenants de teste (gerti_admin_user, BYPASSRLS — idempotente):
  ssh gc 'cd ~/ground-control/apps/sidecar && DATABASE_URL="postgresql+asyncpg://gerti_admin_user:${GERTI_ADMIN_DB_PASSWORD}@postgres:5432/znuny" uv run python scripts/seed_demo_branding.py'
  # Fixture de login Znuny p/ TechNova (1 company + 1 user, dentro do znuny-web como otrs — idempotente):
  ssh gc 'cd ~/ground-control && ./scripts/seed-demo.sh'
  ```
  (`seed_demo_branding.py` requires the #1C `seed_demo_contracts.py` to have run first — Aurora tenant/instance/6 contracts already exist in prod from #1C, so this only adds Aurora branding + the full TechNova tenant. `./scripts/seed-demo.sh` is idempotent and now also runs `scripts/seed-technova.pl` so `admin.tech@technova.example` / `TechNova@Demo2026` authenticates against the real Znuny for tenant 2.)
  Cloudflare ingress for **BOTH** `aurora.suporte.gerti.com.br` AND `technova.suporte.gerti.com.br` -> `http://portal:3000` via the **read-modify-write** pattern (D3 of `docs/superpowers/plans/2026-05-17-spec-1c-deploy.md` §D3 + `.ia/OPS.md`). **Resolve account/tunnel id** exactly like #1C D3: decode the base64 connector token in `.env.prod` (`{"a":<account_id>,"t":<tunnel_id>,...}`) — OR via the CF API (`GET /accounts` → `GET /accounts/{acct}/cfd_tunnel?is_deleted=false` → the tunnel whose `configurations` ingress contains `znuny-dev.was.dev.br`; that is the tunnel `ground-control` — **do NOT confuse with `groundcontrol-landing`**, which serves `groundcontrol.was.dev.br`). The CF API token is in env `CF_API_TOKEN` (scopes `Cloudflare Tunnel:Edit` + `Zone:DNS:Edit`, zone `was.dev.br`). Then: GET the `cfd_tunnel` configuration; with `jq`, first drop any pre-existing `aurora.suporte.gerti.com.br`/`technova.suporte.gerti.com.br` rules (idempotent), then splice **BOTH** new hostname rules immediately BEFORE the trailing `http_status:404` catch-all; **abort-guard (the #1C D3 guard) MUST assert `znuny-dev.was.dev.br` AND `api-dev.was.dev.br` are BOTH still present** in the spliced object AND that BOTH `aurora.suporte.gerti.com.br` and `technova.suporte.gerti.com.br` are present — abort with NO PUT if any of the four is missing; PUT the FULL modified object back; re-GET and assert ALL FOUR hostnames (`znuny-dev.was.dev.br`, `api-dev.was.dev.br`, `aurora.suporte.gerti.com.br`, `technova.suporte.gerti.com.br`) are present and the last element is still `http_status:404`. DNS: idempotent CNAME for BOTH subdomains (check-then-write: `GET /zones/{zone}/dns_records?name=<sub>.suporte.gerti.com.br` → `POST` if absent / `PUT` if present) -> `<tunnel_id>.cfargotunnel.com`, **proxied** (if the token lacks `Zone:DNS:Edit`, create BOTH manually — non-blocking for code). Verify: `curl -fsS https://aurora.suporte.gerti.com.br/ | grep -qi 'Aurora Móveis'` AND `curl -fsS https://technova.suporte.gerti.com.br/ | grep -qi 'TechNova'` (DIFFERENT branding per subdomain) AND `curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login` AND `curl -fsS https://api-dev.was.dev.br/v1/health` (200) AND `curl -fsS https://groundcontrol.was.dev.br >/dev/null` (200) — znuny-dev / api-dev / groundcontrol unchanged. **Never** PUT a hand-written config.
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/Dockerfile apps/portal/.dockerignore docker-compose.yml && git -c commit.gpgsign=false commit -m "feat(#1F-a): serviço portal aditivo no compose + ingress Cloudflare (2 subdomínios aurora+technova, guard znuny-dev+api-dev)"
  ```

---

## Task 15 — Final `.ia/` docs + ADRs D14/D15/D16

**Files:** Modify `.ia/ARCHITECTURE.md` · `.ia/INTEGRATION.md` · `.ia/OPS.md` · `.ia/DECISIONS.md`.

- [ ] **Step 1 — ARCHITECTURE.md.** Add a "Portal Cliente (#1F-a)" section: Nuxt 3 SSR `apps/portal` on networks `app`+`edge`, Nitro branding middleware (subdomain->`/v1/branding`, 60s cache, neutral default), server-proxied auth re-emitting `gsid` first-party, sidecar as the only Znuny door; **two testable white-label tenants** (Aurora `aurora.suporte.gerti.com.br` + TechNova `technova.suporte.gerti.com.br`) on the SAME single Znuny (§2.1), cross-tenant cookie rejection (403) as the white-label proof; topology line `Browser -> cloudflared -> portal:3000 -> sidecar:8001 -> (Znuny GI | gerti schema RLS)`.
- [ ] **Step 2 — INTEGRATION.md.** In "Construído vs pendente", add rows: `tenant_branding` table+RLS (built); `/v1/branding`, `/v1/auth/login`, `/v1/auth/logout`, `/v1/me`, `/v1/contracts` (built); `znuny_gi.authenticate_customer` (built, mechanism per D14); portal SSR (built); 2 white-label test tenants Aurora+TechNova seeded idempotently (`seed_demo_branding.py` + Znuny `scripts/seed-technova.pl` via `scripts/seed-demo.sh`) (built). Note OIDC/#1D still deferred (login-layer swap-only later); branding admin UI / tenant onboarding still #1G (these 2 tenants are seeded test fixtures, not onboarding).
- [ ] **Step 3 — OPS.md.** Add "Deploy do portal (Spec #1F-a — profile `gerti`)": `git pull` + `$DC build portal && $DC up -d portal`; the Cloudflare read-modify-write ingress for **BOTH** `aurora.suporte.gerti.com.br` AND `technova.suporte.gerti.com.br` (account/tunnel id resolved from `.env.prod` connector token base64 or via CF API by the tunnel containing `znuny-dev.was.dev.br` = tunnel `ground-control`, NOT `groundcontrol-landing`; guard preserves `znuny-dev`+`api-dev`; never hand-written PUT); idempotent CNAME for both subdomains; the TechNova Znuny customer fixture (`ssh gc 'cd ~/ground-control && ./scripts/seed-demo.sh'`, idempotent, runs `seed-technova.pl` inside `znuny-web` as `otrs`; demo login `admin.tech@technova.example` / `TechNova@Demo2026`); verification curls (Aurora vs TechNova different branding; znuny-dev/api-dev/groundcontrol 200); rollback (`$DC stop portal`; Znuny untouched; NEVER `make reset`).
- [ ] **Step 4 — DECISIONS.md.** Confirm **D14** present from Task 1 and **D16** present from Task 3 (TenantMiddleware BYPASSRLS resolution path — already authored when the admin path was introduced; do NOT re-author, only verify it is the last-but-one ADR). Append **D15 — Deploy do Portal: serviço aditivo profile-gated, sidecar como única porta**: `portal` (Nuxt 3 SSR) is a `profiles:["gerti"]` compose service; nets `app`+`edge`; talks only to `sidecar:8001`; multi-stage image with build-only deps (runtime `internal:true`); Cloudflare ingress by read-modify-write (same D3 pattern), never hand-written PUT; `SESSION_SECRET` via `${GERTI_SESSION_SECRET:-}` and `DATABASE_ADMIN_URL` from `gerti_admin_user`+`${GERTI_ADMIN_DB_PASSWORD:-}` (never `:?` at compose level — D13 footgun); rollback = `stop portal`, Znuny untouched. Final ADR order: D14 (Task 1), D16 (Task 3), D15 (here).
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add .ia/ARCHITECTURE.md .ia/INTEGRATION.md .ia/OPS.md .ia/DECISIONS.md && git -c commit.gpgsign=false commit -m "docs(#1F-a): ARCHITECTURE/INTEGRATION/OPS + ADR D15 (D14 do spike, D16 do Task 3)"
  ```

---

## Self-Review

### Spec-coverage table (each spec § -> task)

| Spec § | Covered by |
|---|---|
| §1 Objetivo (white-label ponta-a-ponta) | Tasks 2–14 |
| §2.1 Sempre 1 Znuny | Tasks 1, 5, 8 (TechNova aponta para a MESMA única `gerti.znuny_instance`; nenhuma instância nova) |
| §2.2 Tudo white-label, default neutro | Tasks 8 (2 tenants brandeados, paletas distintas), 10 (`DEFAULT_BRANDING` != Gerti) |
| §2.3 Auth mínima = credencial Znuny via sidecar | Tasks 1, 4, 5, 6 |
| §2.4 Uma visão: contratos+saldo (#1C) | Task 7 |
| §2.5 Portal em apps/portal Nuxt 3 SSR | Tasks 9–12 |
| §3 Arquitetura (reusa TenantMiddleware/GUC) | Tasks 3 (D16: narrow BYPASSRLS resolution path; data stays RLS-subject), 4, 7 |
| §4.1 migration 0011_tenant_branding + RLS | Task 2 |
| §4.2 GET /v1/branding | Task 3 |
| §4.2 POST /v1/auth/login + logout | Task 6 |
| §4.2 GET /v1/me | Task 4 |
| §4.2 GET /v1/contracts | Task 7 |
| §4.2 get_current_session seam | Task 4 |
| §4.2 znuny_gi.authenticate_customer | Tasks 1, 5 |
| §4.3 Nitro branding middleware (no flash) | Tasks 10, 12 |
| §4.3 /login, /, logout + proxy routes | Tasks 11, 12 |
| §4.3 tema CSS vars / config | Tasks 9, 12 |
| §5 Fluxos (não-auth, login, autenticado) | Tasks 3, 6, 7, 12, 13 |
| §6 Erros & segurança (404/401/403/503, anti cross-tenant) | Tasks 3, 4, 6 (H3/H5/H6); Task 13 e2e prova rejeição 403 cross-tenant entre Aurora↔TechNova |
| §7 R1 spike + ADR fallback | Task 1 |
| §7 R2 cookie cross-subdomínio | Tasks 4, 6 (SameSite=Lax + tenant check) |
| §7 R3 flash | Tasks 10, 12 (H11) |
| §8 Testes sidecar | Tasks 2–8, 13 |
| §8 Testes portal (Vitest) | Tasks 10, 13 |
| §8 E2E smoke | Task 13 (cross-tenant white-label isolation: branding diferente por subdomínio, contratos por tenant, cookie cross-tenant 403) |
| §9 YAGNI (exclusions) | **ABSENT by construction — see below** |
| §10 Definição de pronto | Tasks 13 (e2e), 14 (deploy aditivo), 15 (.ia) |

### YAGNI exclusion confirmation

No task, file, or step creates or mentions as work: OIDC/PKCE flow or `useOidc`; ticket listing/detail/creation; service catalog or dynamic form renderer; executive dashboards/KPIs; billing approval; **branding admin UI; tenant onboarding automation**; logo upload (logo is an external `logo_url` string only); i18n; multi-Znuny / dedicated instances. Auth is exclusively username/password -> sidecar -> Znuny GI (`authenticate_customer`) -> JWT HS256 `gsid` cookie. The only authenticated data view is the tenant's contracts+balance via #1C `ConsumptionService.balance`. The **2 white-label test tenants (Aurora + TechNova)** are an APPROVED scoped-breadth change (user decision): still strictly "branding + portal vertical slice", just ×2, so cross-tenant isolation is *demonstrable* rather than asserted on faith. TechNova is created exclusively by **idempotent seed scripts** (`seed_demo_branding.py` + `scripts/seed-technova.pl`, the latter a minimal 1-company/1-user Znuny test fixture exactly like #1C's Aurora Znuny seed) — there is NO admin UI, NO onboarding flow, NO new Znuny instance, NO API to create tenants. This is NOT a §9/YAGNI breach. **Confirmed absent.**

### Placeholder scan

Targets `TODO`, `FIXME`, `similar to Task`, `add error handling`, `<placeholder>`, bare `...`: none present in any task, including the amended Task 8 (full runnable `seed_demo_branding.py` + full runnable `scripts/seed-technova.pl`) and Task 13 (full runnable e2e). Every code step contains complete, runnable code. The only conditionals are (a) Task 5's note that the implementation follows D14's decided mechanism (PRIMARY shown in full; FALLBACK explicitly bounded to the identical public signature) — a spike-driven decision point, not a placeholder; and (b) the "Executing subagent" verification notes in Tasks 8/13 telling the worker to confirm real seed counts/exported names before relying on numeric assertions — these are explicit verification instructions, not unfinished code. The public contracts are frozen and identical either way.

### Type / name consistency check

- `authenticate_customer(login: str, password: str) -> bool` + `ZnunyUnavailable(RuntimeError)` — contracted Task 1 (D14), defined Task 5, consumed Tasks 6 & 13 identically.
- `get_current_session(request, settings) -> SessionPayload` — defined Task 4, consumed Tasks 4 (`/v1/me`) & 7 (`/v1/contracts`); 401 (no tenant/cookie) vs 403 (tenant mismatch) per H6, tested in Tasks 4 & 7.
- `encode_session(tenant_id: str, customer_login: str, settings) -> str` — Task 4; used by Task 6 + tests 4/7/13; `tenant_id` always `str(tenant.id)`.
- Cookie name `gsid` = `settings.session_cookie_name` everywhere (Tasks 4, 6, 9–13).
- `tenant_branding` table / `0011_tenant_branding` revision / `TenantBranding` model — Task 2; S1 set extended (H2); consumed Tasks 3, 4, 7, 8, 13.
- `database_admin_url` (`Settings`, optional) / `admin_engine` / `AdminSessionLocal` (`db.py`) — introduced Task 3 (H15, ADR D16); `init_db`/`dispose_db` updated Task 3; `TenantMiddleware` uses `AdminSessionLocal or SessionLocal` for subdomain resolution ONLY; bound to the admin `engine` in the test wiring of Tasks 3, 4, 6, 7, 13 (mirrors `test_tenant_middleware.py`); compose `DATABASE_ADMIN_URL` Task 14; ADR is **D16** (D14/D15 unchanged). Spelled identically everywhere.
- `Balance.kind`/`Balance.remaining` from #1C `ConsumptionService` — read-only in Task 7 (`Saldo` mirrors fields exactly), asserted Tasks 7 & 13.
- `seed` importable from `seed_demo_branding` — signature **`async def seed(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]`** returning `(aurora_tenant_id, technova_tenant_id)`; defined Task 8, consumed Tasks 8 & 13 identically (Task 13 destructures `aurora_id, technova_id = await seed_demo_branding.seed(session)`). It reuses `seed_demo_contracts`' module-level `INSTANCE_NAME`/`START`/`END` and the deterministic-uuid5/append-only-safe ConsumptionEvent pattern; Aurora branding only (tenant/instance/contracts are #1C's), full TechNova tenant on the SAME single `znuny_instance`.
- New TechNova identifiers — spelled IDENTICALLY across Tasks 8, 13, 14 & docs: `znuny_customer_id='TECHNOVA'`, `subdomain='technova'`, hostname `technova.suporte.gerti.com.br`, `display_name="TechNova"`, Znuny CustomerCompany CustomerID `TECHNOVA`, customer login `admin.tech@technova.example`, demo password `TechNova@Demo2026` (same `<Marca>@Demo2026` convention as Aurora's `Aurora@Demo2026`), seeder `scripts/seed-technova.pl` wired into `scripts/seed-demo.sh`.
- Test counts monotonic & consistent from the verified baseline 34: Task 2 +1 (35), Task 3 +2 (37 — the D16 admin-path test in 3A and the branding-router test in 3B), Task 4 +1 (38), Task 5 +1 (39), Task 6 +1 (40), Task 7 +1 (41), Task 8 +1 (42 — the single `test_branding_seed_two_tenants_idempotent` function), Task 13 +1 sidecar e2e smoke (43 — the single `test_portal_vertical_slice_two_tenants` function; the strengthened cross-tenant assertions are added WITHIN that one function, not as new test functions). Sequence: 34 -> 35 -> 37 -> 38 -> 39 -> 40 -> 41 -> 42 -> 43 (Task 1 = no test, spike-only; Tasks 9–12 portal-only). The 2-tenant breadth adds NO new sidecar test *functions* (the existing Task 8 and Task 13 functions were broadened in place), so every subsequent stated count is unchanged and the progression stays arithmetically monotonic; **new final sidecar gate count = 43 passed**. Each step's stated count equals the previous task's count plus exactly the number of new test functions that task adds; the only +2 step (Task 3) adds exactly two test files with one test function each.

- ADR numbering: **D14** (Task 1, R1 auth spike) and **D16** (Task 3, TenantMiddleware BYPASSRLS resolution path) are authored where introduced; **D15** (Task 15, portal deploy) is unchanged in intent. D14/D15 content was NOT altered by this amendment; only D16 is new. Final order in `.ia/DECISIONS.md`: D14, D16, D15.

All gaps found during self-review were fixed inline before saving: the gate critical defect (H15 — `TenantMiddleware` resolving the FORCE-RLS `gerti.tenant` lookup through an RLS-subject session, returning a false 404 for every valid subdomain in prod and silently inverting every router-test assertion) is fixed by introducing the narrow BYPASSRLS resolution path (ADR D16) folded into Task 3 and by rewiring Tasks 3/4/6/7/13 to bind `db.AdminSessionLocal` to the admin `engine` (mirroring `test_tenant_middleware.py`) while the tenant DATA path stays RLS-subject; `/v1/contracts` RLS is genuinely exercised because `get_tenant_session` uses module `db.SessionLocal`=`app_session_factory` (RLS-subject) under the GUC (explicit decision recorded in Task 7's preamble); S1 set extension wired into Task 2 Step 1; `branding-context` server endpoint added in Task 12 so the layout's `useAsyncData` has a real source; `sidecar` joined to the `app` network in Task 14 so `portal` can reach it; Task 14 ingress guard widened to also assert the pre-existing `api-dev` hostname survives the splice (consistent with #1C D3).

**2-tenant breadth amendment (approved scoped change, this revision):** Task 8 now seeds TWO testable white-label tenants — Aurora (branding row only; tenant/instance/6 contracts remain #1C's) and a new fictitious TechNova (its own `gerti.tenant` + `tenant_branding` with a deliberately distinct violet/dark palette + a small 2-contract set, all on the SAME single `gerti.znuny_instance` per §2.1, reusing `seed_demo_contracts`' deterministic-uuid5/append-only-safe pattern) plus a minimal idempotent Znuny `CustomerCompany`/`CustomerUser` fixture (`scripts/seed-technova.pl`, login `admin.tech@technova.example` / `TechNova@Demo2026`, wired into `scripts/seed-demo.sh`) so `POST /v1/auth/login` validates tenant 2 against the real Znuny exactly like Aurora. `seed_demo_branding.seed()` now returns `(aurora_id, technova_id)` and Task 13's e2e is the cross-tenant white-label proof (different branding per subdomain; per-tenant contract isolation; `gsid` minted for tenant A rejected 403 on tenant B). Task 14 splices BOTH `aurora.suporte`/`technova.suporte` hostnames in ONE D3 read-modify-write while the #1C D3 abort-guard asserts `znuny-dev`+`api-dev` BOTH survive; idempotent CNAME for both. H16 records the trap+fix. No new sidecar test *functions* (the Task 8 and Task 13 functions were broadened in place), so the gate progression is unchanged and monotonic — **final sidecar gate = 43 passed**. Scope unchanged: nothing from Spec §9 YAGNI added (no admin UI, no onboarding automation, no OIDC, no tickets/catalog/dashboards — TechNova is a seeded test fixture, not onboarding); Task 1's R1 spike untouched; the `0011` RLS template untouched; the Task 3 BYPASSRLS/ADR-D16 fix untouched; ADR numbering (D14 spike / D15 deploy / D16 middleware) untouched.
