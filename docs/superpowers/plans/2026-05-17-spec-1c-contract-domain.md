# Spec #1C — Contract Domain Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real contract engine of the Gerti Service Desk sidecar — the 6 MSP contract types, billing≠closing cycles, hour-bank, append-only consumption, glosa, index adjustment, renewal, and per-tenant RLS — as a tested, demoable domain core (models + migrations + repositories + services). No HTTP endpoints (Spec #1E).

**Architecture:** Extends the Plano 1A sidecar foundation (`apps/sidecar`, repo `ground-control` branch `main`, alembic chain head `0004_contract_enums`, `TenantMiddleware`, FORCE RLS on `gerti.tenant`). Adds a request/job tenant-scoped session seam that sets the `app.current_tenant` Postgres GUC, a reusable RLS migration pattern (`ENABLE`+`FORCE ROW LEVEL SECURITY`, policy keyed strictly on `current_setting('app.current_tenant', true)::uuid` with **no empty-GUC escape**), the contract data model from Spec #0 §4, tenant-scoped repositories, and domain services for create/consume/close-cycle/adjust/renew. All DDL runs as `gerti_admin` (never `gerti_app`-owned). Tests use the existing testcontainers Postgres and assert isolation under the unprivileged `gerti_sidecar` role.

---

## AUDIT — REAL CURRENT STATE (2026-05-17, verified by commands)

**Repo:** `ground-control` `git@github.com:williamroot/ground-control.git`, branch `main`, HEAD `e02d4fc` (`feat(repo): consolidar sidecar+infra+specs no monorepo`). Working tree clean.

**Alembic versions present** (`apps/sidecar/alembic/versions/`): `0001_initial_schema.py` (rev `0001_initial`, down `None`), `0002_rls_baseline.py` (rev `0002_rls_baseline`, down `0001_initial`), `0003_force_rls_tenant.py` (rev `0003_force_rls_tenant`, down `0002_rls_baseline`), `0004_contract_enums.py` (rev `0004_contract_enums`, down `0003_force_rls_tenant`). **Chain head = `0004_contract_enums`.** New migrations MUST start `down_revision="0004_contract_enums"`.

**Models present:** `base.py`, `enums.py`, `tenant.py`, `znuny_instance.py` (+ `__init__.py` exporting `Base, Tenant, ZnunyInstance`). **No contract-domain models yet.**

**Tests present (16, all green):** `test_config`, `test_db_connection`, `test_enums`, `test_health`, `test_models`, `test_rls_isolation`, `test_tenant_middleware`, `test_tenant_session`. conftest already has `app_db_url`, `app_session_factory`, `seed_two_tenants`, `_reset_settings_cache`.

**Gate result (quoted, verified):** `uv sync --all-extras` exit 0; `ruff check .` → "All checks passed!"; `ruff format --check .` → "28 files already formatted"; `mypy src` → "Success: no issues found in 13 source files"; `pytest -q` → **`16 passed in 5.17s`**.

### T1 (✅ DONE — committed, green)
`db.tenant_session_scope(tenant_id, *, factory=None)` + `db.get_tenant_session(request)` exist in `db.py` using `SELECT set_config('app.current_tenant', :tid, true)` (the `SET LOCAL`-can't-bind trap is already fixed). `0003_force_rls_tenant.py` FORCEs RLS on `gerti.tenant` and replaces the empty-GUC-escape policy with strict `id = current_setting('app.current_tenant', true)::uuid`. `test_tenant_session.py` proves fail-closed under the unprivileged `gerti_sidecar` role (`app_session_factory`). **Evidence:** both files present; `test_tenant_session_scope_sets_guc_and_isolates` + `test_unset_guc_sees_zero_tenant_rows` pass.

### T2 (✅ DONE — committed, green, AST-verified)
`models/enums.py` has `ContractType, ContractStatus, CycleKind, CycleStatus, GlosaStatus, BillingStatus` as `StrEnum`. `0004_contract_enums.py` issues `CREATE TYPE gerti.<name> AS ENUM (...)` for all six. `test_enums.py` asserts exact value ordering. **Cross-checked against Spec #0 §4 — identical** (`contract_type`: closed_value,credit_brl,credit_shared,hour_bank,saas_product,service_count; `contract_status`: draft,active,suspended,expired,terminated; `cycle_kind`: billing,closing; `cycle_status`: open,closed,invoiced; `glosa_status`: pending,approved,rejected; `billing_status`: pending,approved,billed,disputed). No change needed.

**=> The actionable plan starts at Task 3. Tasks 1 & 2 below are retained for traceability and marked ✅ DONE; do NOT re-run their migration-creation steps (the revisions already exist). Their `down_revision` text in this doc reflects the OLD pre-consolidation chain; the REAL committed files are `0003`/`0004` as audited above and are correct.**

### CRITICAL HARDENING APPLIED TO TASKS 3–13 (read before implementing)

The following latent defects were found by static analysis of the plan against the audited code and Postgres semantics. **Each fix is baked into the task below; the trap → fix table:**

| # | Trap | Fix (mandatory) |
|---|---|---|
| H1 | Native ENUM column with `server_default="active"` renders bare `DEFAULT 'active'`; Postgres will NOT implicitly cast an unknown-typed literal default to `gerti.contract_status` reliably under all clients → migration/insert error. | In **migrations** use `server_default=sa.text("'active'::gerti.contract_status")` (and `'open'::gerti.cycle_status`, `'pending'::gerti.glosa_status`, `'pending'::gerti.billing_status`). In **models** use `server_default=text("'active'::gerti.contract_status")` etc. (import `from sqlalchemy import text`). |
| H2 | Append-only trigger on `consumption_event` blocks ALL UPDATE — but `CycleService.close()` MUST `UPDATE ... SET closing_cycle_id` and glosa flow sets `glosa_id`. The plan as written deadlocks: closing any cycle raises the append-only exception. | Trigger blocks **DELETE always** and blocks **UPDATE unless the only changed columns are `closing_cycle_id` and/or `glosa_id`** (immutable ledger fields stay immutable; settlement bookkeeping allowed). Exact plpgsql given in Task 6. |
| H3 | `contract.shared_pool_id` FK targets `gerti.shared_credit_pool`, created in `0006` (Task 5) AFTER `contract` in `0005` (Task 3). Inline FK in `0005` → "relation gerti.shared_credit_pool does not exist". | `0005` creates `shared_pool_id` column **without** FK. `0006` adds it **after** `shared_credit_pool` exists via explicit `op.create_foreign_key("fk_contract_shared_pool_id_shared_credit_pool", "contract", "shared_credit_pool", ["shared_pool_id"], ["id"], source_schema="gerti", referent_schema="gerti")`; `0006.downgrade()` drops this FK first. Exact code in Tasks 3 & 5. |
| H4 | `consumption_event.id` declared `BigInteger primary_key autoincrement=True`. Under `op.create_table` with an explicit PK column, SQLAlchemy emits `BIGINT` with **no sequence** (no `BIGSERIAL`), so inserts without explicit id fail NOT NULL. Spec #0 says `BIGSERIAL`. | Migration column: `sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True)`. Model: `mapped_column(BigInteger, sa.Identity(always=False), primary_key=True)`. |
| H5 | `cycle.closed_at = func.now()` then same-session `await s.get(ContractCycle, cyc.id)` returns the identity-mapped object whose `closed_at` is the unflushed SQL clause / stale `None`; `assert refreshed.closed_at is not None` is flaky. | Assign a Python value: `cycle.closed_at = dt.datetime.now(dt.UTC)` in `CycleService.close()`. Deterministic, timezone-aware, asserts cleanly. |
| H6 | conftest testcontainer pins `postgres:16` but prod cluster (`docker-compose.yml`) is `postgres:18`. Matview uses `COUNT(ce.*)` + `FILTER` — valid on both, but version drift is a zero-tolerance smell and the spec DDL header says PG16. | Bump conftest to `PostgresContainer("postgres:18", driver="asyncpg")` in Task 3 Step 0 (one-line conftest change, run full gate to prove still 16/16). Removes prod/test engine drift. |
| H7 | Child-table RLS policies (`contract_id IN (SELECT ... WHERE tenant_id = GUC)`) were `USING`-only. For INSERT, Postgres applies `WITH CHECK`; if absent it falls back to `USING`, so a cross-tenant INSERT via a child table under tenant A's GUC could succeed if the subquery is satisfiable. | Every child-table policy gets an explicit identical `WITH CHECK (...)` mirroring `USING`. Baked into Tasks 3/5/6/7. |
| H8 | `Glosa.consumption_event_id` is `BIGINT` FK to `consumption_event.id`; `consumption_event.glosa_id` is `UUID` with **no** FK (deliberate, avoids circular FK). Plan models are correct but unstated — an implementer might "fix" it into a circular FK. | Explicitly: `consumption_event.glosa_id` is `UUID` **NO ForeignKey** (settled-by pointer, enforced in app layer). Documented in Task 6. |
| H9 | `ContractService._current_tenant_id()` does `import uuid` inside the method and `from sqlalchemy import text` inside the method — ruff `PLC0415` (import-outside-toplevel) may fail the gate depending on ruff config. | Move `import uuid` and `from sqlalchemy import text` to module top of `contract_service.py`. Baked into Task 9. |
| H10 | `contract.updated_at` has no `onupdate`; `AdjustmentService`/`CycleService` mutate the contract but `updated_at` never advances (silent staleness). | Model: add `onupdate=func.now()` to `updated_at`. (DB-side trigger out of scope; ORM `onupdate` is sufficient for sidecar-mediated writes — all writes go through the ORM.) Baked into Task 3. |
| H11 | T13 e2e has dead `hasattr(... '_session_contracts')` probe that never exists → ruff `B004`/unused. | Delete the probe lines entirely; keep only the explicit `select(Contract.code)` assertion. Baked into Task 13. |

**Tech Stack:** Python 3.12, uv, FastAPI (only the `Depends` seam — no routes here), SQLAlchemy 2 async, Alembic, asyncpg, Pydantic v2, pytest + pytest-asyncio + testcontainers, PostgreSQL (schema `gerti`, RLS).

---

## Foundation facts (from Plano 1A — do not re-derive)

- Package: `apps/sidecar`, `uv` manager. Gate: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q` (all green).
- `src/gerti_sidecar/`: `config.py` (`get_settings()` is `@lru_cache`), `db.py` (module globals `engine`/`SessionLocal`; helpers `make_engine`, `make_session_factory`, `get_session`, `session_scope`, `init_db`, `dispose_db` — globals referenced as `db.X`, never value-imported), `models/base.py` (`Base`, `metadata` has `schema="gerti"` + `NAMING_CONVENTION`), `models/__init__.py` (exports `Base`, `Tenant`, `ZnunyInstance`), `middleware/tenant.py` (`TenantMiddleware` sets `request.state.tenant` to a `Tenant`), `main.py` (`create_app()` + module-level `app`).
- Alembic: `alembic/versions/0001_initial_schema.py` (rev `0001_initial`; `gerti.tenant`, `gerti.znuny_instance`), `0002_rls_baseline.py` (rev `0002_rls_baseline`, down `0001_initial`; RLS on `gerti.tenant` with policy `tenant_self_isolation` that has an empty-GUC escape `current_setting('app.current_tenant', true) = '' OR id = ...::uuid`). New migrations chain after `0002_rls_baseline`.
- Postgres init (`infra/compose/postgres/init/001_schemas_and_roles.sql`): schemas `gerti`,`znuny`; roles `gerti_app` (NOLOGIN), `gerti_admin` (BYPASSRLS), `znuny_owner`; users `gerti_sidecar` IN ROLE `gerti_app` (NOT bypassrls), `gerti_admin_user` IN ROLE `gerti_admin` (bypassrls), `znuny`. Password (dev) `dev_change_me`.
- `tests/conftest.py`: session-scoped testcontainers `postgres` running the init SQL; function-scoped `engine` fixture runs Alembic `upgrade head`/`downgrade base`; `session` fixture (admin connection, rolls back); autouse `_reset_settings_cache`. Cross-tenant/RLS tests open a SECOND engine as `gerti_sidecar` (unprivileged) to prove isolation; seeding is done via the admin `engine`.
- Migrations must NEVER `CREATE SCHEMA` (init owns schemas). DDL objects must be created such that `gerti_admin` owns them (migrations run via the admin DSN) and `gerti_app` only gets `GRANT`s — `gerti_app` must never own a table.

---

## File Structure

Created/modified by this plan (all under `apps/sidecar/`):

```
src/gerti_sidecar/
  db.py                                 MODIFY: add get_tenant_session() dep + tenant_session_scope() ctx mgr
  models/
    __init__.py                         MODIFY: export new models
    enums.py                            CREATE: StrEnum types (contract_type, statuses, cycle kinds…)
    contract.py                         CREATE: Contract, ContractBillingParty
    catalog.py                          CREATE: ServiceCatalogItem, SharedCreditPool
    contract_scope.py                   CREATE: ContractScopeService, ContractScopeCi
    contract_policy.py                  CREATE: ContractAdjustmentRule, ContractRenewalPolicy
    cycle.py                            CREATE: ContractCycle
    consumption.py                      CREATE: ConsumptionEvent, Glosa
    ticket_link.py                      CREATE: TicketContractLink
  repositories/
    __init__.py                         CREATE
    base.py                             CREATE: TenantScopedRepository[T]
    contract.py                         CREATE: ContractRepository
    cycle.py                            CREATE: ContractCycleRepository
    consumption.py                      CREATE: ConsumptionEventRepository, GlosaRepository
  domain/
    __init__.py                         CREATE
    errors.py                           CREATE: domain exceptions
    contract_service.py                 CREATE: create/validate by 6 types
    consumption_service.py              CREATE: idempotent append-only recording + balance
    cycle_service.py                    CREATE: close cycle (billing≠closing, overage, accrual, glosa)
    adjustment_service.py               CREATE: index reajuste + renewal
alembic/versions/
  0003_force_rls_tenant.py              CREATE: FORCE RLS on gerti.tenant + grants
  0004_contract_enums.py                CREATE: CREATE TYPE gerti.* enums
  0005_contract_core.py                 CREATE: contract, contract_billing_party (+RLS template)
  0006_catalog_scope.py                 CREATE: service_catalog_item, shared_credit_pool, scope tables
  0007_cycle_consumption.py             CREATE: contract_cycle, consumption_event, glosa
  0008_policy_ticketlink.py             CREATE: adjustment_rule, renewal_policy, ticket_contract_link
  0009_balance_view.py                  CREATE: contract_balance_current materialized view
tests/
  conftest.py                           MODIFY: add app_session_factory (gerti_sidecar) + seed helpers
  test_tenant_session.py                CREATE
  test_rls_contract_tables.py           CREATE
  test_contract_service.py              CREATE
  test_consumption_service.py           CREATE
  test_cycle_service.py                 CREATE
  test_adjustment_service.py            CREATE
  test_contract_domain_e2e.py           CREATE
scripts/
  demo_contract.py                      CREATE: domain-level demo (no HTTP) printing a full lifecycle
```

**Naming locked (use verbatim everywhere):**
Postgres enum types in schema `gerti`: `contract_type` (`closed_value,credit_brl,credit_shared,hour_bank,saas_product,service_count`), `contract_status` (`draft,active,suspended,expired,terminated`), `cycle_kind` (`billing,closing`), `cycle_status` (`open,closed,invoiced`), `glosa_status` (`pending,approved,rejected`), `billing_status` (`pending,approved,billed,disputed`).
Python enums (`models/enums.py`) mirror them as `StrEnum`: `ContractType`, `ContractStatus`, `CycleKind`, `CycleStatus`, `GlosaStatus`, `BillingStatus`.
Model classes: `Contract`, `ContractBillingParty`, `ServiceCatalogItem`, `SharedCreditPool`, `ContractScopeService`, `ContractScopeCi`, `ContractAdjustmentRule`, `ContractRenewalPolicy`, `ContractCycle`, `ConsumptionEvent`, `Glosa`, `TicketContractLink`.
Session seam: `db.get_tenant_session` (FastAPI dep), `db.tenant_session_scope(tenant_id)` (async ctx mgr).
GUC name: `app.current_tenant`. RLS policy name per table: `<table>_tenant_isolation`.

---

## Task 1: Tenant-scoped session seam + FORCE RLS backfill on `gerti.tenant` — ✅ DONE

> **STATUS: ✅ COMPLETE & VERIFIED** — `db.tenant_session_scope`/`get_tenant_session` shipped (uses `SELECT set_config('app.current_tenant', :tid, true)`), `0003_force_rls_tenant.py` committed (rev `0003_force_rls_tenant`, down `0002_rls_baseline`), `test_tenant_session.py` green under unprivileged role. **Do NOT re-create the migration or re-run these steps.** Steps below retained for traceability only (the doc's `down_revision` text predates the consolidation; the committed file is authoritative).

Closes the Plano 1A foundation gap: requests/jobs must run DB work with `SET LOCAL app.current_tenant`, and `gerti.tenant` must `FORCE` RLS so even the owner is constrained. Negative test proves an unset GUC sees zero rows.

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/db.py`
- Create: `apps/sidecar/alembic/versions/0003_force_rls_tenant.py`
- Modify: `apps/sidecar/tests/conftest.py`
- Create: `apps/sidecar/tests/test_tenant_session.py`

- [ ] **Step 1: Write the failing test**

Create `apps/sidecar/tests/test_tenant_session.py`:

```python
"""tenant_session_scope sets app.current_tenant and RLS isolates tenant rows."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from gerti_sidecar import db
from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.mark.asyncio
async def test_tenant_session_scope_sets_guc_and_isolates(app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        rows = (await s.execute(text("SELECT id FROM gerti.tenant"))).scalars().all()
        guc = (await s.execute(text("SELECT current_setting('app.current_tenant', true)"))).scalar_one()
    assert {str(r) for r in rows} == {str(a_id)}
    assert guc == str(a_id)


@pytest.mark.asyncio
async def test_unset_guc_sees_zero_tenant_rows(app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    factory = app_session_factory
    async with factory() as s:  # no tenant_session_scope → GUC unset
        rows = (await s.execute(text("SELECT id FROM gerti.tenant"))).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Add the conftest fixtures the test needs**

In `apps/sidecar/tests/conftest.py`, add (keep existing imports; add what's missing):

```python
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.fixture
def app_db_url(db_url: str) -> str:
    """Same DB as `db_url` but as the unprivileged gerti_sidecar role (RLS applies)."""
    # db_url is the testcontainers admin URL; swap user:pass to gerti_sidecar.
    after_at = db_url.split("@", 1)[1]
    return f"postgresql+asyncpg://gerti_sidecar:dev_change_me@{after_at}"


@pytest.fixture
async def app_session_factory(engine, app_db_url):
    """async_sessionmaker bound to a gerti_sidecar (RLS-subject) engine.

    `engine` fixture has already applied Alembic head on the shared DB.
    """
    app_engine = create_async_engine(app_db_url, echo=False)
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    yield factory
    await app_engine.dispose()


@pytest.fixture
async def seed_two_tenants(session) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed two tenants via the admin session (bypasses RLS for setup)."""
    inst = ZnunyInstance(
        name="main", base_url="http://znuny", db_dsn_secret_ref="x",
        webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
    )
    session.add(inst)
    await session.flush()
    a = Tenant(legal_name="A SA", trade_name="A", document="1",
               znuny_customer_id="a", znuny_instance_id=inst.id, subdomain="a")
    b = Tenant(legal_name="B SA", trade_name="B", document="2",
               znuny_customer_id="b", znuny_instance_id=inst.id, subdomain="b")
    session.add_all([a, b])
    await session.commit()
    return a.id, b.id
```

(If `engine`/`session`/`db_url` fixture names differ in the current conftest, adapt to the real names — read conftest first; the intent is: admin seeding + a separate `gerti_sidecar` factory.)

- [ ] **Step 3: Run the test — expect failure**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_tenant_session.py -q`
Expected: FAIL — `AttributeError: module 'gerti_sidecar.db' has no attribute 'tenant_session_scope'` (and, once that exists, the unset-GUC test still fails because `gerti.tenant` policy has the `=''` escape from `0002`).

- [ ] **Step 4: Add the session seam to `db.py`**

Append to `apps/sidecar/src/gerti_sidecar/db.py` (keep existing code; add imports `from collections.abc import AsyncIterator`, `from contextlib import asynccontextmanager`, `import uuid`, `from sqlalchemy import text`, `from fastapi import Request`, `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker` if not already imported):

```python
@asynccontextmanager
async def tenant_session_scope(
    tenant_id: uuid.UUID,
    *,
    factory: "async_sessionmaker[AsyncSession] | None" = None,
) -> "AsyncIterator[AsyncSession]":
    """Yield a session with `app.current_tenant` set for the whole transaction.

    SET LOCAL is transaction-scoped, so we open an explicit transaction and
    set the GUC inside it before yielding. Commits on success, rolls back on
    error. `factory` overrides the module SessionLocal (tests/jobs).
    """
    sm = factory if factory is not None else SessionLocal
    if sm is None:
        raise RuntimeError("DB não inicializado — chame init_db() no lifespan")
    async with sm() as session:
        async with session.begin():
            # Postgres SET LOCAL não aceita bind params no asyncpg; o
            # equivalente canônico é set_config(...,true) (transaction-local,
            # parametrizado/injection-safe, mesma GUC/semântica).
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session


async def get_tenant_session(request: Request) -> "AsyncIterator[AsyncSession]":
    """FastAPI dependency: tenant-scoped session for tenant-bound routes.

    Requires TenantMiddleware to have set request.state.tenant. Raises if
    absent (route is tenant-scoped but no tenant was resolved).
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise RuntimeError("get_tenant_session usado em rota sem tenant resolvido")
    async with tenant_session_scope(tenant.id) as session:
        yield session
```

- [ ] **Step 5: Create migration `0003_force_rls_tenant.py`**

Create `apps/sidecar/alembic/versions/0003_force_rls_tenant.py`:

```python
"""force RLS on gerti.tenant + drop empty-GUC escape for contract safety

Revision ID: 0003_force_rls_tenant
Revises: 0002_rls_baseline
Create Date: 2026-05-17
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_force_rls_tenant"
down_revision: str | None = "0002_rls_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Owner must also obey RLS (defense-in-depth; gerti_admin still BYPASSRLS).
    op.execute("ALTER TABLE gerti.tenant FORCE ROW LEVEL SECURITY")
    # Replace the permissive self-isolation policy: NO empty-GUC escape.
    op.execute("DROP POLICY IF EXISTS tenant_self_isolation ON gerti.tenant")
    op.execute(
        """
        CREATE POLICY tenant_tenant_isolation ON gerti.tenant
            USING (id = current_setting('app.current_tenant', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_tenant_isolation ON gerti.tenant")
    op.execute(
        """
        CREATE POLICY tenant_self_isolation ON gerti.tenant
            USING (
                current_setting('app.current_tenant', true) = ''
                OR id = current_setting('app.current_tenant', true)::uuid
            )
        """
    )
    op.execute("ALTER TABLE gerti.tenant NO FORCE ROW LEVEL SECURITY")
```

Note: `current_setting('app.current_tenant', true)` returns NULL when unset → `id = NULL::uuid` is NULL → row excluded ⇒ fail-closed (zero rows), exactly what the negative test asserts.

- [ ] **Step 6: Run tests — expect pass**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_tenant_session.py -q`
Expected: 2 passed (GUC set + isolation; unset GUC → 0 rows).

- [ ] **Step 7: Full gate**

Run: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q`
Expected: all green (existing suite + the 2 new tests). Fix ruff/mypy nits inline (annotate fixture return types, e.g. `AsyncIterator[...]`).

- [ ] **Step 8: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/db.py apps/sidecar/alembic/versions/0003_force_rls_tenant.py apps/sidecar/tests/conftest.py apps/sidecar/tests/test_tenant_session.py
git commit -m "feat(sidecar): tenant_session_scope + get_tenant_session dep + FORCE RLS em gerti.tenant"
```

---

## Task 2: Contract enums (Python + Postgres) + RLS migration helper — ✅ DONE

> **STATUS: ✅ COMPLETE & VERIFIED** — `models/enums.py` (6 `StrEnum`s) + `0004_contract_enums.py` (rev `0004_contract_enums`, down `0003_force_rls_tenant`, `CREATE TYPE gerti.*`) committed; `test_enums.py` green; values cross-checked identical to Spec #0 §4. **Do NOT re-create.** Steps retained for traceability.

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/enums.py`
- Create: `apps/sidecar/alembic/versions/0004_contract_enums.py`
- Create: `apps/sidecar/tests/test_enums.py`

- [ ] **Step 1: Failing test**

Create `apps/sidecar/tests/test_enums.py`:

```python
from gerti_sidecar.models.enums import (
    BillingStatus, ContractStatus, ContractType, CycleKind, CycleStatus, GlosaStatus,
)


def test_enum_values_match_db_contract():
    assert [e.value for e in ContractType] == [
        "closed_value", "credit_brl", "credit_shared",
        "hour_bank", "saas_product", "service_count",
    ]
    assert [e.value for e in ContractStatus] == [
        "draft", "active", "suspended", "expired", "terminated",
    ]
    assert [e.value for e in CycleKind] == ["billing", "closing"]
    assert [e.value for e in CycleStatus] == ["open", "closed", "invoiced"]
    assert [e.value for e in GlosaStatus] == ["pending", "approved", "rejected"]
    assert [e.value for e in BillingStatus] == ["pending", "approved", "billed", "disputed"]
    assert ContractType.hour_bank == "hour_bank"  # StrEnum behaviour
```

- [ ] **Step 2: Run — expect fail**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_enums.py -q`
Expected: `ModuleNotFoundError: No module named 'gerti_sidecar.models.enums'`.

- [ ] **Step 3: Implement enums**

Create `apps/sidecar/src/gerti_sidecar/models/enums.py`:

```python
"""Enum types shared by the contract domain (mirror gerti.* Postgres enums)."""
from __future__ import annotations

from enum import StrEnum


class ContractType(StrEnum):
    closed_value = "closed_value"
    credit_brl = "credit_brl"
    credit_shared = "credit_shared"
    hour_bank = "hour_bank"
    saas_product = "saas_product"
    service_count = "service_count"


class ContractStatus(StrEnum):
    draft = "draft"
    active = "active"
    suspended = "suspended"
    expired = "expired"
    terminated = "terminated"


class CycleKind(StrEnum):
    billing = "billing"
    closing = "closing"


class CycleStatus(StrEnum):
    open = "open"
    closed = "closed"
    invoiced = "invoiced"


class GlosaStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BillingStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    billed = "billed"
    disputed = "disputed"
```

- [ ] **Step 4: Create migration `0004_contract_enums.py`**

Create `apps/sidecar/alembic/versions/0004_contract_enums.py`:

```python
"""create gerti.* enum types for the contract domain

Revision ID: 0004_contract_enums
Revises: 0003_force_rls_tenant
Create Date: 2026-05-17
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_contract_enums"
down_revision: str | None = "0003_force_rls_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUMS = {
    "contract_type": ("closed_value", "credit_brl", "credit_shared",
                       "hour_bank", "saas_product", "service_count"),
    "contract_status": ("draft", "active", "suspended", "expired", "terminated"),
    "cycle_kind": ("billing", "closing"),
    "cycle_status": ("open", "closed", "invoiced"),
    "glosa_status": ("pending", "approved", "rejected"),
    "billing_status": ("pending", "approved", "billed", "disputed"),
}


def upgrade() -> None:
    for name, values in _ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE gerti.{name} AS ENUM ({vals})")


def downgrade() -> None:
    for name in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS gerti.{name}")
```

- [ ] **Step 5: Run tests — expect pass**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_enums.py -q`
Expected: 1 passed.

- [ ] **Step 6: Apply + verify migration on dev Postgres (optional sanity)**

The conftest `engine` fixture already runs `alembic upgrade head`; the full suite running green proves `0004` applies. No manual step required.

- [ ] **Step 7: Gate + commit**

Run the full gate (Task 1 Step 7 command). Then:

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/models/enums.py apps/sidecar/alembic/versions/0004_contract_enums.py apps/sidecar/tests/test_enums.py
git commit -m "feat(sidecar): enums do domínio de contratos (Python + tipos gerti.*)"
```

---

## Task 3: `Contract` + `ContractBillingParty` models + migration with RLS template — START HERE (true current head)

This task LOCKS the reusable RLS table template every later contract table copies. **Migration `0005_contract_core.py` chains `down_revision="0004_contract_enums"` (the audited real head).**

**Files:**
- Modify: `apps/sidecar/tests/conftest.py` (H6 testcontainer bump)
- Create: `apps/sidecar/src/gerti_sidecar/models/contract.py`
- Modify: `apps/sidecar/src/gerti_sidecar/models/__init__.py`
- Create: `apps/sidecar/alembic/versions/0005_contract_core.py`
- Create: `apps/sidecar/tests/test_model_contract.py`

- [ ] **Step 0: H6 — align testcontainer to prod Postgres major**

In `apps/sidecar/tests/conftest.py` change exactly:
```python
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
```
to:
```python
    with PostgresContainer("postgres:18", driver="asyncpg") as pg:
```
Run the full gate now (`ruff check . && ruff format --check . && mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q`) and confirm still **16 passed** before proceeding. Commit alone:
```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/tests/conftest.py
git commit -m "test(sidecar): alinhar testcontainer ao postgres:18 de produção (remove drift PG16/PG18)"
```

- [ ] **Step 1: Failing test**

Create `apps/sidecar/tests/test_model_contract.py`:

```python
import datetime as dt
import uuid

import pytest

from gerti_sidecar.models import Contract, ContractBillingParty
from gerti_sidecar.models.enums import ContractStatus, ContractType


@pytest.mark.asyncio
async def test_create_contract_and_billing_party(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(
        tenant_id=a_id, code="CTR-2026-0001", type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
        initial_hours=40, unit_price_brl=180, billing_period_months=1,
        closing_period_months=3, created_by="william",
    )
    session.add(c)
    await session.flush()
    assert c.id is not None
    assert c.status == ContractStatus.active
    assert c.accumulate_balance_between_cycles is False

    bp = ContractBillingParty(
        contract_id=c.id, legal_name="A SA", document="1",
        fiscal_address={"city": "São Paulo", "uf": "SP"},
    )
    session.add(bp)
    await session.flush()
    assert bp.contract_id == c.id
```

- [ ] **Step 2: Run — expect fail**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_contract.py -q`
Expected: `ImportError: cannot import name 'Contract'`.

- [ ] **Step 3: Implement models**

Create `apps/sidecar/src/gerti_sidecar/models/contract.py`:

```python
"""Contract + ContractBillingParty (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import ContractStatus, ContractType

# H1: native enum defaults MUST be explicitly cast to the gerti.* type.
_contract_type = ENUM(ContractType, name="contract_type", schema="gerti", create_type=False)
_contract_status = ENUM(ContractStatus, name="contract_status", schema="gerti", create_type=False)


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_id_code"),
        CheckConstraint("ends_on > starts_on", name="ck_contract_dates"),
        CheckConstraint(
            "closing_period_months % billing_period_months = 0 "
            "OR billing_period_months % closing_period_months = 0",
            name="ck_contract_cycle_multiple",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[ContractType] = mapped_column(_contract_type, nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        _contract_status,
        nullable=False,
        server_default=text("'active'::gerti.contract_status"),  # H1
    )
    starts_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[dt.date] = mapped_column(Date, nullable=False)

    initial_amount_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    initial_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    initial_service_count: Mapped[int | None] = mapped_column(Integer)
    unit_price_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    travel_franchise_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    billing_period_months: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    closing_period_months: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    billing_in_advance: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    accumulate_balance_between_cycles: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    shared_pool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.shared_credit_pool.id")
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),  # H10: advance on any ORM-mediated mutation
    )


class ContractBillingParty(Base):
    __tablename__ = "contract_billing_party"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[str] = mapped_column(String, nullable=False)
    fiscal_address: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String)
```

`models/__init__.py`: add `from gerti_sidecar.models.contract import Contract, ContractBillingParty` and extend `__all__`.

- [ ] **Step 4: Migration `0005_contract_core.py` (defines the RLS template)**

Create `apps/sidecar/alembic/versions/0005_contract_core.py`:

```python
"""contract + contract_billing_party with the per-tenant RLS template

Revision ID: 0005_contract_core
Revises: 0004_contract_enums
Create Date: 2026-05-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_contract_core"
down_revision: str | None = "0004_contract_enums"  # AUDITED REAL HEAD
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
    """Reusable RLS template for per-tenant contract tables.

    - ENABLE + FORCE so even the table owner obeys it.
    - Policy strictly keyed on the GUC cast to uuid (NO empty-GUC escape):
      unset GUC → current_setting(...) NULL → comparison NULL → 0 rows
      (fail-closed). Contract data must never leak with an unset tenant.
    - gerti_app gets table + sequence DML grants (it never owns objects).
    """
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        f"USING ({tenant_col} = current_setting('app.current_tenant', true)::uuid) "
        f"WITH CHECK ({tenant_col} = current_setting('app.current_tenant', true)::uuid)"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app"
    )


def _disable_tenant_rls(table: str) -> None:
    op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
    op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
    op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "contract",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("gerti.tenant.id"), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("type",
                  postgresql.ENUM(name="contract_type", schema="gerti", create_type=False),
                  nullable=False),
        sa.Column("status",
                  postgresql.ENUM(name="contract_status", schema="gerti", create_type=False),
                  nullable=False,
                  server_default=sa.text("'active'::gerti.contract_status")),  # H1
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("initial_amount_brl", sa.Numeric(14, 2)),
        sa.Column("initial_hours", sa.Numeric(10, 2)),
        sa.Column("initial_service_count", sa.Integer()),
        sa.Column("unit_price_brl", sa.Numeric(14, 2)),
        sa.Column("travel_franchise_count", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("billing_period_months", sa.Integer(),
                  nullable=False, server_default="1"),
        sa.Column("closing_period_months", sa.Integer(),
                  nullable=False, server_default="1"),
        sa.Column("billing_in_advance", sa.Boolean(),
                  nullable=False, server_default=sa.text("true")),
        sa.Column("accumulate_balance_between_cycles", sa.Boolean(),
                  nullable=False, server_default=sa.text("false")),
        # H3: column only — FK to gerti.shared_credit_pool is added in 0006
        # (Task 5), AFTER that table exists. Do NOT add sa.ForeignKey here.
        sa.Column("shared_pool_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_id_code"),
        sa.CheckConstraint("ends_on > starts_on", name="ck_contract_dates"),
        sa.CheckConstraint(
            "closing_period_months % billing_period_months = 0 "
            "OR billing_period_months % closing_period_months = 0",
            name="ck_contract_cycle_multiple",
        ),
        schema="gerti",
    )
    op.create_index("ix_contract_tenant_status", "contract",
                    ["tenant_id", "status"], schema="gerti")
    # Spec #0 §4 partial indexes (were missing from the draft plan):
    op.create_index("ix_contract_ends_on_active", "contract", ["ends_on"],
                    schema="gerti", postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_contract_shared_pool_id", "contract", ["shared_pool_id"],
                    schema="gerti",
                    postgresql_where=sa.text("shared_pool_id IS NOT NULL"))
    op.create_table(
        "contract_billing_party",
        sa.Column("contract_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("legal_name", sa.String(), nullable=False),
        sa.Column("document", sa.String(), nullable=False),
        sa.Column("fiscal_address", postgresql.JSONB(), nullable=False),
        sa.Column("payment_method", sa.String()),
        schema="gerti",
    )
    _enable_tenant_rls("contract")
    # contract_billing_party has no tenant_id; isolate via its contract.
    op.execute("ALTER TABLE gerti.contract_billing_party ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_billing_party FORCE ROW LEVEL SECURITY")
    # H7: child-table policy needs explicit WITH CHECK identical to USING,
    # else cross-tenant INSERT could slip through the USING fallback.
    op.execute(
        "CREATE POLICY contract_billing_party_tenant_isolation "
        "ON gerti.contract_billing_party "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "current_setting('app.current_tenant', true)::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "current_setting('app.current_tenant', true)::uuid))"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.contract_billing_party "
        "TO gerti_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.contract_billing_party FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS contract_billing_party_tenant_isolation "
               "ON gerti.contract_billing_party")
    op.drop_table("contract_billing_party", schema="gerti")
    _disable_tenant_rls("contract")
    op.drop_index("ix_contract_shared_pool_id", table_name="contract", schema="gerti")
    op.drop_index("ix_contract_ends_on_active", table_name="contract", schema="gerti")
    op.drop_index("ix_contract_tenant_status", table_name="contract", schema="gerti")
    op.drop_table("contract", schema="gerti")
```

> **RLS TEMPLATE — every later per-tenant contract table copies `_enable_tenant_rls`/`_disable_tenant_rls` verbatim** (paste the helpers into each later migration; Alembic migrations must be self-contained — do not import across revisions). Child tables without their own `tenant_id` use the `contract_id IN (SELECT ... WHERE tenant_id = GUC)` form shown for `contract_billing_party`.

- [ ] **Step 5: Run model test — expect pass**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_contract.py -q`
Expected: 1 passed (seeding via admin `session` bypasses RLS).

- [ ] **Step 6: Gate + commit**

Run the full gate. Then:

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/models/contract.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/alembic/versions/0005_contract_core.py apps/sidecar/tests/test_model_contract.py
git commit -m "feat(sidecar): modelos Contract/ContractBillingParty + template RLS por tabela"
```

---

## Task 4: RLS enforcement test for contract tables (negative + cross-tenant)

Proves the template actually isolates, under the unprivileged role — not theatre.

**Files:**
- Create: `apps/sidecar/tests/test_rls_contract_tables.py`

- [ ] **Step 1: Write the test**

Create `apps/sidecar/tests/test_rls_contract_tables.py`:

```python
"""Contract RLS: unprivileged role, fail-closed on unset GUC, cross-tenant blocked."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from gerti_sidecar import db
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractType


async def _seed_contract(session, tenant_id, code):
    c = Contract(tenant_id=tenant_id, code=code, type=ContractType.credit_brl,
                 starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                 initial_amount_brl=10000, created_by="seed")
    session.add(c)
    await session.flush()
    return c.id


@pytest.mark.asyncio
async def test_contract_rls(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    await _seed_contract(session, a_id, "A-1")
    await _seed_contract(session, b_id, "B-1")
    await session.commit()

    # tenant A scope → only A's contract
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        codes = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert codes == ["A-1"]

    # tenant B scope → only B's
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        codes = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert codes == ["B-1"]

    # unset GUC → zero rows (fail-closed, no empty escape)
    async with app_session_factory() as s:
        rows = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert rows == []

    # WITH CHECK: inserting a row for another tenant under A's GUC is rejected
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        with pytest.raises(Exception):  # noqa: B017  (RLS WITH CHECK violation)
            await s.execute(
                text("INSERT INTO gerti.contract "
                     "(tenant_id, code, type, starts_on, ends_on, created_by) "
                     "VALUES (:t, 'X', 'credit_brl', '2026-01-01', '2026-12-31', 's')"),
                {"t": str(b_id)},
            )
```

- [ ] **Step 2: Run — expect pass** (template already implemented in Task 3)

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_rls_contract_tables.py -q`
Expected: 1 passed. If the WITH CHECK assertion fails, the policy is missing `WITH CHECK` — fix `0005` to include it (it does per Task 3) and re-run.

- [ ] **Step 3: Gate + commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/tests/test_rls_contract_tables.py
git commit -m "test(sidecar): RLS de contrato — fail-closed, cross-tenant e WITH CHECK"
```

---

## Task 5: Catalog + scope + pool models + migration

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/catalog.py`, `apps/sidecar/src/gerti_sidecar/models/contract_scope.py`
- Modify: `apps/sidecar/src/gerti_sidecar/models/__init__.py`
- Create: `apps/sidecar/alembic/versions/0006_catalog_scope.py`
- Create: `apps/sidecar/tests/test_model_catalog.py`

- [ ] **Step 1: Failing test**

Create `apps/sidecar/tests/test_model_catalog.py`:

```python
import datetime as dt
import pytest

from gerti_sidecar.models import (
    ServiceCatalogItem, SharedCreditPool, ContractScopeService, ContractScopeCi, Contract,
)
from gerti_sidecar.models.enums import ContractType, CycleKind


@pytest.mark.asyncio
async def test_catalog_pool_scope(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    svc = ServiceCatalogItem(tenant_id=a_id, code="M365", title="Microsoft 365",
                             default_queue_name="Suporte::N1", unit_price_brl=120)
    pool = SharedCreditPool(tenant_id=a_id, name="Pool Matriz",
                            total_amount_brl=50000, cycle_kind=CycleKind.billing,
                            cycle_period_months=1, current_cycle_start=dt.date(2026, 1, 1))
    session.add_all([svc, pool])
    await session.flush()
    c = Contract(tenant_id=a_id, code="C1", type=ContractType.closed_value,
                 starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                 created_by="s")
    session.add(c)
    await session.flush()
    session.add(ContractScopeService(contract_id=c.id, service_id=svc.id))
    session.add(ContractScopeCi(contract_id=c.id, znuny_ci_id=4012,
                                covered_from=dt.date(2026, 1, 1)))
    await session.flush()
    assert svc.id and pool.id
```

- [ ] **Step 2: Run — expect fail** (`ImportError: cannot import name 'ServiceCatalogItem'`)

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_catalog.py -q`

- [ ] **Step 3: Implement `models/catalog.py`**

```python
"""ServiceCatalogItem + SharedCreditPool (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func, text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import CycleKind

_cycle_kind = ENUM(CycleKind, name="cycle_kind", schema="gerti", create_type=False)


class ServiceCatalogItem(Base):
    __tablename__ = "service_catalog_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"))
    code: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    default_queue_name: Mapped[str] = mapped_column(String, nullable=False)
    default_priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="3")
    default_sla_minutes: Mapped[int | None] = mapped_column(Integer)
    form_schema: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"))  # H1-class
    unit_price_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    active: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class SharedCreditPool(Base):
    __tablename__ = "shared_credit_pool"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    total_amount_brl: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cycle_kind: Mapped[CycleKind] = mapped_column(_cycle_kind, nullable=False)
    cycle_period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    current_cycle_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
```

Create `apps/sidecar/src/gerti_sidecar/models/contract_scope.py`:

```python
"""ContractScopeService + ContractScopeCi (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ContractScopeService(Base):
    __tablename__ = "contract_scope_service"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.service_catalog_item.id"),
        primary_key=True)
    unit_price_override: Mapped[float | None] = mapped_column(Numeric(14, 2))


class ContractScopeCi(Base):
    __tablename__ = "contract_scope_ci"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True)
    znuny_ci_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covered_from: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    covered_until: Mapped[dt.date | None] = mapped_column(Date)
```

Extend `models/__init__.py` exports + `__all__`.

- [ ] **Step 4: Migration `0006_catalog_scope.py`**

Create `apps/sidecar/alembic/versions/0006_catalog_scope.py` — `revision="0006_catalog_scope"`, `down_revision="0005_contract_core"`. Create the 4 tables (`service_catalog_item`, `shared_credit_pool`, `contract_scope_service`, `contract_scope_ci`) with the same `sa.Column` shapes as the models above, schema `gerti`. **`form_schema` JSONB server_default must be `sa.text("'{}'::jsonb")`** (a bare `"{}"` string default fails on JSONB). **Paste the `_enable_tenant_rls`/`_disable_tenant_rls` helpers from Task 3 verbatim into this migration** (self-contained).

**Order inside `upgrade()` (MANDATORY):**
1. `op.create_table("shared_credit_pool", ...)` FIRST (it is referenced by the FK added next).
2. **H3 — add the deferred FK from `contract.shared_pool_id`:**
   ```python
   op.create_foreign_key(
       "fk_contract_shared_pool_id_shared_credit_pool",
       "contract", "shared_credit_pool",
       ["shared_pool_id"], ["id"],
       source_schema="gerti", referent_schema="gerti",
   )
   op.create_index("ix_shared_credit_pool_tenant_id", "shared_credit_pool",
                   ["tenant_id"], schema="gerti")  # Spec #0 §4
   ```
3. `op.create_table("service_catalog_item", ...)`, then `contract_scope_service`, then `contract_scope_ci`.

RLS (all ENABLE+FORCE, GRANT `SELECT,INSERT,UPDATE,DELETE` to `gerti_app`):
- `service_catalog_item`: `tenant_id` is NULLable (global catalog rows). Policy: `USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true)::uuid)` and **`WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)`** (global rows are read-only to tenants; seed global rows as `gerti_admin`).
- `shared_credit_pool`: `_enable_tenant_rls("shared_credit_pool")` (has `tenant_id`; the helper already includes `WITH CHECK`).
- `contract_scope_service` / `contract_scope_ci`: no `tenant_id` — **H7**: both `USING` AND `WITH CHECK` = `contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid)`, ENABLE+FORCE, GRANT.

`downgrade()` (FK-safe reverse order): drop scope tables → drop policies/grants → `op.drop_constraint("fk_contract_shared_pool_id_shared_credit_pool", "contract", schema="gerti", type_="foreignkey")` → drop `ix_shared_credit_pool_tenant_id` → drop `service_catalog_item` → drop `shared_credit_pool`.

- [ ] **Step 5: Run model test — expect pass**; then full gate.

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_catalog.py -q` → 1 passed. Then the full gate (all green).

- [ ] **Step 6: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/models/catalog.py apps/sidecar/src/gerti_sidecar/models/contract_scope.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/alembic/versions/0006_catalog_scope.py apps/sidecar/tests/test_model_catalog.py
git commit -m "feat(sidecar): catálogo de serviços, pool compartilhado e escopo de contrato (+RLS)"
```

---

## Task 6: Cycle + consumption + glosa models + migration (append-only)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/cycle.py`, `consumption.py`
- Modify: `models/__init__.py`
- Create: `apps/sidecar/alembic/versions/0007_cycle_consumption.py`
- Create: `apps/sidecar/tests/test_model_cycle_consumption.py`

- [ ] **Step 1: Failing test**

Create `apps/sidecar/tests/test_model_cycle_consumption.py`:

```python
import datetime as dt
import pytest
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.models import Contract, ContractCycle, ConsumptionEvent, Glosa
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus, GlosaStatus


@pytest.mark.asyncio
async def test_cycle_consumption_glosa(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(tenant_id=a_id, code="C1", type=ContractType.hour_bank,
                 starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                 initial_hours=40, unit_price_brl=180, created_by="s")
    session.add(c)
    await session.flush()
    cyc = ContractCycle(contract_id=c.id, kind=CycleKind.closing,
                        period_start=dt.date(2026, 1, 1), period_end=dt.date(2026, 3, 31))
    session.add(cyc)
    await session.flush()
    assert cyc.status == CycleStatus.open

    ev = ConsumptionEvent(
        contract_id=c.id, occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
        source_kind="ticket_work", source_ref="znuny:article:1",
        billable_minutes=30, billable_amount_brl=0, recorded_by="tec",
        webhook_event_id="11111111-1111-1111-1111-111111111111")
    session.add(ev)
    await session.flush()

    # idempotency: same webhook_event_id rejected
    dup = ConsumptionEvent(
        contract_id=c.id, occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
        source_kind="ticket_work", source_ref="znuny:article:1",
        billable_minutes=30, billable_amount_brl=0, recorded_by="tec",
        webhook_event_id="11111111-1111-1111-1111-111111111111")
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    g = Glosa(consumption_event_id=ev.id, reason="fora do escopo",
              requested_by="cliente")
    session.add(g)
    await session.flush()
    assert g.status == GlosaStatus.pending
```

- [ ] **Step 2: Run — expect fail** (`ImportError: cannot import name 'ContractCycle'`).

- [ ] **Step 3: Implement `models/cycle.py`**

```python
"""ContractCycle (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import CycleKind, CycleStatus

_cycle_kind = ENUM(CycleKind, name="cycle_kind", schema="gerti", create_type=False)
_cycle_status = ENUM(CycleStatus, name="cycle_status", schema="gerti", create_type=False)


class ContractCycle(Base):
    __tablename__ = "contract_cycle"
    __table_args__ = (
        UniqueConstraint("contract_id", "kind", "period_start",
                         name="uq_contract_cycle_contract_id_kind_period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False)
    kind: Mapped[CycleKind] = mapped_column(_cycle_kind, nullable=False)
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[CycleStatus] = mapped_column(
        _cycle_status, nullable=False,
        server_default=text("'open'::gerti.cycle_status"))  # H1
    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    totals: Mapped[dict | None] = mapped_column(JSONB)
```

Implement `models/consumption.py`:

```python
"""ConsumptionEvent (append-only) + Glosa (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Identity, Numeric, String, func, text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import GlosaStatus

_glosa_status = ENUM(GlosaStatus, name="glosa_status", schema="gerti", create_type=False)


class ConsumptionEvent(Base):
    __tablename__ = "consumption_event"

    # H4: BIGSERIAL-equivalent — Identity makes the sequence; plain
    # autoincrement under op.create_table with explicit PK does NOT.
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str] = mapped_column(String, nullable=False)
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.service_catalog_item.id"))
    billable_minutes: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0")
    billable_amount_brl: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0")
    unit_price_at_event: Mapped[float | None] = mapped_column(Numeric(14, 2))
    # H8: settled-by pointer. UUID, NO ForeignKey (a FK here would create a
    # circular FK with gerti.glosa). Integrity enforced in the app layer.
    glosa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closing_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract_cycle.id"))
    recorded_by: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Glosa(Base):
    __tablename__ = "glosa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    consumption_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("gerti.consumption_event.id"), nullable=False)
    status: Mapped[GlosaStatus] = mapped_column(
        _glosa_status, nullable=False,
        server_default=text("'pending'::gerti.glosa_status"))  # H1
    reason: Mapped[str] = mapped_column(String, nullable=False)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_note: Mapped[str | None] = mapped_column(String)
```

Extend `models/__init__.py`.

- [ ] **Step 4: Migration `0007_cycle_consumption.py`**

`revision="0007_cycle_consumption"`, `down_revision="0006_catalog_scope"`. Create `contract_cycle`, `consumption_event`, `glosa` with the EXACT column shapes from the models above. Migration-side specifics:

- **H1 enum defaults:** `contract_cycle.status` → `server_default=sa.text("'open'::gerti.cycle_status")`; `glosa.status` → `server_default=sa.text("'pending'::gerti.glosa_status")`.
- **H4:** `consumption_event.id` column = `sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True)`. `glosa.consumption_event_id` = `sa.Column(..., sa.BigInteger(), sa.ForeignKey("gerti.consumption_event.id"), nullable=False)`.
- **H8:** `consumption_event.glosa_id` = `sa.Column("glosa_id", postgresql.UUID(as_uuid=True))` — **NO `sa.ForeignKey`**.
- Constraints/indexes: `UNIQUE (contract_id, kind, period_start)` on `contract_cycle` (`uq_contract_cycle_contract_id_kind_period_start`); `CREATE INDEX ON gerti.contract_cycle (contract_id, status)`; partial `CREATE INDEX ix_contract_cycle_period_end_open ON gerti.contract_cycle (period_end) WHERE status = 'open'`; partial unique `CREATE UNIQUE INDEX consumption_event_idempotency ON gerti.consumption_event (webhook_event_id) WHERE webhook_event_id IS NOT NULL`; `CREATE INDEX ON gerti.consumption_event (contract_id, occurred_at DESC)`; `CREATE INDEX ON gerti.consumption_event (closing_cycle_id)`; `CREATE INDEX ON gerti.consumption_event (source_ref)`; `CREATE INDEX ON gerti.glosa (consumption_event_id)`; `CREATE INDEX ON gerti.glosa (status)`.

**H2 — append-only enforcement that does NOT break cycle closing / glosa settlement.** A blanket UPDATE block deadlocks `CycleService.close()` (which sets `closing_cycle_id`) and the glosa flow (which sets `glosa_id`). The ledger fields stay immutable; only the two settlement-bookkeeping columns may change; DELETE is always forbidden:

```python
op.execute(
    """
    CREATE OR REPLACE FUNCTION gerti.consumption_event_append_only()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'consumption_event é append-only (DELETE proibido)';
        END IF;
        -- UPDATE: only closing_cycle_id and/or glosa_id may change.
        IF ROW(NEW.id, NEW.contract_id, NEW.occurred_at, NEW.source_kind,
                NEW.source_ref, NEW.service_id, NEW.billable_minutes,
                NEW.billable_amount_brl, NEW.unit_price_at_event,
                NEW.recorded_by, NEW.recorded_at, NEW.webhook_event_id)
           IS DISTINCT FROM
           ROW(OLD.id, OLD.contract_id, OLD.occurred_at, OLD.source_kind,
                OLD.source_ref, OLD.service_id, OLD.billable_minutes,
                OLD.billable_amount_brl, OLD.unit_price_at_event,
                OLD.recorded_by, OLD.recorded_at, OLD.webhook_event_id)
        THEN
            RAISE EXCEPTION 'consumption_event é append-only: só closing_cycle_id/glosa_id podem mudar';
        END IF;
        RETURN NEW;
    END;
    $$;
    """
)
op.execute(
    "CREATE TRIGGER trg_consumption_event_append_only "
    "BEFORE UPDATE OR DELETE ON gerti.consumption_event "
    "FOR EACH ROW EXECUTE FUNCTION gerti.consumption_event_append_only()"
)
```

Paste the Task 3 `_enable_tenant_rls`/`_disable_tenant_rls` helpers verbatim (self-contained). Apply per-tenant RLS to all three (none has its own `tenant_id`) — **H7**: each policy has BOTH `USING` and `WITH CHECK`:
- `contract_cycle` / `consumption_event`: `(contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid))` for both `USING` and `WITH CHECK`.
- `glosa`: `(consumption_event_id IN (SELECT ce.id FROM gerti.consumption_event ce JOIN gerti.contract c ON c.id = ce.contract_id WHERE c.tenant_id = current_setting('app.current_tenant', true)::uuid))` for both.

ENABLE+FORCE on all three. Grants (minimal): `GRANT SELECT, INSERT, UPDATE ON gerti.consumption_event TO gerti_app` (UPDATE needed for the settlement columns; the trigger still forbids ledger mutation and DELETE — RLS + trigger + grant are now consistent); `GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.contract_cycle TO gerti_app`; `GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.glosa TO gerti_app`.

`downgrade()` (FK-safe order): drop glosa (policy/grant/table) → drop trigger `trg_consumption_event_append_only` ON consumption_event → `DROP FUNCTION IF EXISTS gerti.consumption_event_append_only()` → drop consumption_event (policy/grant/indexes/table) → drop contract_cycle (policy/grant/indexes/table).

- [ ] **Step 5: Run model test — expect pass**; full gate green.

- [ ] **Step 6: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/models/cycle.py apps/sidecar/src/gerti_sidecar/models/consumption.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/alembic/versions/0007_cycle_consumption.py apps/sidecar/tests/test_model_cycle_consumption.py
git commit -m "feat(sidecar): ciclo, consumo append-only (trigger+idempotência) e glosa (+RLS)"
```

---

## Task 7: Policy + ticket-link models + migration

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/contract_policy.py`, `ticket_link.py`
- Modify: `models/__init__.py`
- Create: `apps/sidecar/alembic/versions/0008_policy_ticketlink.py`
- Create: `apps/sidecar/tests/test_model_policy_link.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import pytest

from gerti_sidecar.models import (
    Contract, ContractAdjustmentRule, ContractRenewalPolicy, TicketContractLink,
)
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_policy_and_ticket_link(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(tenant_id=a_id, code="C1", type=ContractType.hour_bank,
                 starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                 initial_hours=40, created_by="s")
    session.add(c)
    await session.flush()
    session.add(ContractAdjustmentRule(contract_id=c.id, index_code="IPCA",
                cadence_months=12, next_run_on=dt.date(2027, 1, 1)))
    session.add(ContractRenewalPolicy(contract_id=c.id, auto_renew=True,
                notice_days=30, next_review_on=dt.date(2026, 11, 1)))
    session.add(TicketContractLink(znuny_ticket_id=12345, contract_id=c.id,
                tenant_id=a_id, linked_by_rule="auto:default"))
    await session.flush()
    link = await session.get(TicketContractLink, 12345)
    assert link.contract_id == c.id and link.billing_status == "pending"
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement models**

`models/contract_policy.py`:

```python
"""ContractAdjustmentRule + ContractRenewalPolicy (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ContractAdjustmentRule(Base):
    __tablename__ = "contract_adjustment_rule"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True)
    index_code: Mapped[str] = mapped_column(String, nullable=False)
    cadence_months: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    cap_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    last_applied_on: Mapped[dt.date | None] = mapped_column(Date)
    last_applied_percent: Mapped[float | None] = mapped_column(Numeric(6, 3))


class ContractRenewalPolicy(Base):
    __tablename__ = "contract_renewal_policy"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True)
    auto_renew: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    notice_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30")
    next_review_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    renewal_term_months: Mapped[int | None] = mapped_column(Integer)
```

`models/ticket_link.py`:

```python
"""TicketContractLink (Spec #0 §4)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import BillingStatus

_billing_status = ENUM(BillingStatus, name="billing_status", schema="gerti",
                       create_type=False)


class TicketContractLink(Base):
    __tablename__ = "ticket_contract_link"

    znuny_ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False)
    billing_status: Mapped[BillingStatus] = mapped_column(
        _billing_status, nullable=False,
        server_default=text("'pending'::gerti.billing_status"))  # H1
    linked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    linked_by_rule: Mapped[str] = mapped_column(String, nullable=False)
```

Extend `models/__init__.py`.

- [ ] **Step 4: Migration `0008_policy_ticketlink.py`** — `revision="0008_policy_ticketlink"`, `down_revision="0007_cycle_consumption"`. Create the 3 tables (`contract_adjustment_rule`, `contract_renewal_policy`, `ticket_contract_link`). **H1:** `ticket_contract_link.billing_status` → `server_default=sa.text("'pending'::gerti.billing_status")`. Spec #0 §4 indexes: `CREATE INDEX ON gerti.ticket_contract_link (contract_id)` and `CREATE INDEX ON gerti.ticket_contract_link (tenant_id, billing_status)`. RLS (paste Task 3 helpers verbatim, self-contained): `ticket_contract_link` has `tenant_id` → `_enable_tenant_rls("ticket_contract_link")` (helper already adds `WITH CHECK`); the two policy tables are `contract_id`-only → **H7**: both `USING` AND `WITH CHECK` = `contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid)`, ENABLE+FORCE, GRANT `SELECT,INSERT,UPDATE,DELETE` to gerti_app. `downgrade()` reverses (drop indexes, policies, grants, tables; FK-safe).

- [ ] **Step 5: Run model test — expect pass; full gate green.**

- [ ] **Step 6: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/models/contract_policy.py apps/sidecar/src/gerti_sidecar/models/ticket_link.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/alembic/versions/0008_policy_ticketlink.py apps/sidecar/tests/test_model_policy_link.py
git commit -m "feat(sidecar): regras de reajuste/renovação e vínculo ticket↔contrato (+RLS)"
```

---

## Task 8: Tenant-scoped repositories

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/repositories/__init__.py`, `base.py`, `contract.py`, `cycle.py`, `consumption.py`
- Create: `apps/sidecar/tests/test_repositories.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import pytest

from gerti_sidecar import db
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractType
from gerti_sidecar.repositories.contract import ContractRepository


@pytest.mark.asyncio
async def test_contract_repo_scoped(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    for tid, code in ((a_id, "A1"), (b_id, "B1")):
        session.add(Contract(tenant_id=tid, code=code, type=ContractType.credit_brl,
                    starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                    initial_amount_brl=1000, created_by="s"))
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        repo = ContractRepository(s)
        rows = await repo.list()
        assert [c.code for c in rows] == ["A1"]
        got = await repo.get_by_code("A1")
        assert got is not None and got.tenant_id == a_id
        assert await repo.get_by_code("B1") is None  # RLS hides B
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: gerti_sidecar.repositories`).

- [ ] **Step 3: Implement repositories**

`repositories/__init__.py`: `"""Tenant-scoped repositories."""`

`repositories/base.py`:

```python
"""Generic tenant-scoped repository. RLS does the filtering; these are thin."""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models.base import Base

T = TypeVar("T", bound=Base)


class TenantScopedRepository(Generic[T]):
    """Assumes the session was opened via db.tenant_session_scope (GUC set);
    RLS guarantees only the current tenant's rows are visible/writable."""

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[T]:
        res = await self.session.execute(select(self.model))
        return list(res.scalars().all())

    async def add(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        return obj
```

`repositories/contract.py`:

```python
from __future__ import annotations

from sqlalchemy import select

from gerti_sidecar.models import Contract
from gerti_sidecar.repositories.base import TenantScopedRepository


class ContractRepository(TenantScopedRepository[Contract]):
    model = Contract

    async def get_by_code(self, code: str) -> Contract | None:
        res = await self.session.execute(
            select(Contract).where(Contract.code == code)
        )
        return res.scalar_one_or_none()
```

`repositories/cycle.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select

from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import CycleKind, CycleStatus
from gerti_sidecar.repositories.base import TenantScopedRepository


class ContractCycleRepository(TenantScopedRepository[ContractCycle]):
    model = ContractCycle

    async def open_closing_cycles(self) -> list[ContractCycle]:
        res = await self.session.execute(
            select(ContractCycle).where(
                ContractCycle.kind == CycleKind.closing,
                ContractCycle.status == CycleStatus.open,
            )
        )
        return list(res.scalars().all())

    async def get(self, cycle_id: uuid.UUID) -> ContractCycle | None:
        return await self.session.get(ContractCycle, cycle_id)
```

`repositories/consumption.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select

from gerti_sidecar.models import ConsumptionEvent, Glosa
from gerti_sidecar.repositories.base import TenantScopedRepository


class ConsumptionEventRepository(TenantScopedRepository[ConsumptionEvent]):
    model = ConsumptionEvent

    async def by_webhook_event_id(
        self, webhook_event_id: uuid.UUID
    ) -> ConsumptionEvent | None:
        res = await self.session.execute(
            select(ConsumptionEvent).where(
                ConsumptionEvent.webhook_event_id == webhook_event_id
            )
        )
        return res.scalar_one_or_none()

    async def for_contract(
        self, contract_id: uuid.UUID
    ) -> list[ConsumptionEvent]:
        res = await self.session.execute(
            select(ConsumptionEvent).where(
                ConsumptionEvent.contract_id == contract_id
            )
        )
        return list(res.scalars().all())


class GlosaRepository(TenantScopedRepository[Glosa]):
    model = Glosa
```

- [ ] **Step 4: Run repo test — expect pass; full gate green.**

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/repositories apps/sidecar/tests/test_repositories.py
git commit -m "feat(sidecar): repositórios tenant-scoped (Contract/Cycle/Consumption/Glosa)"
```

---

## Task 9: Contract domain service — create + validate the 6 types

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/__init__.py`, `errors.py`, `contract_service.py`
- Create: `apps/sidecar/tests/test_contract_service.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_create_hour_bank_ok_and_validation(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = ContractService(s)
        c = await svc.create(NewContract(
            code="CTR-1", type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
            initial_hours=40, unit_price_brl=180,
            billing_period_months=1, closing_period_months=3,
            created_by="william"))
        assert c.id is not None and c.type == ContractType.hour_bank

        with pytest.raises(ContractValidationError):  # hour_bank requires initial_hours
            await svc.create(NewContract(
                code="CTR-2", type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                created_by="x"))

        with pytest.raises(ContractValidationError):  # ends<=starts
            await svc.create(NewContract(
                code="CTR-3", type=ContractType.credit_brl,
                starts_on=dt.date(2026, 12, 31), ends_on=dt.date(2026, 1, 1),
                initial_amount_brl=1000, created_by="x"))

        with pytest.raises(ContractValidationError):  # duplicate code in tenant
            await svc.create(NewContract(
                code="CTR-1", type=ContractType.credit_brl,
                starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                initial_amount_brl=1000, created_by="x"))
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

`domain/__init__.py`: `"""Contract domain services."""`

`domain/errors.py`:

```python
"""Domain exceptions for the contract engine."""
from __future__ import annotations


class DomainError(Exception):
    """Base for contract-domain errors."""


class ContractValidationError(DomainError):
    """Invalid contract input or violated invariant."""


class ConsumptionError(DomainError):
    """Invalid consumption recording."""


class CycleError(DomainError):
    """Invalid cycle operation."""
```

`domain/contract_service.py`:

```python
"""Create/validate contracts honoring the 6 MSP contract types (Spec #0 §4)."""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractType


@dataclasses.dataclass(slots=True)
class NewContract:
    code: str
    type: ContractType
    starts_on: dt.date
    ends_on: dt.date
    created_by: str
    initial_amount_brl: float | None = None
    initial_hours: float | None = None
    initial_service_count: int | None = None
    unit_price_brl: float | None = None
    travel_franchise_count: int = 0
    billing_period_months: int = 1
    closing_period_months: int = 1
    billing_in_advance: bool = True
    accumulate_balance_between_cycles: bool = False


# Which "initial_*" field each type requires.
_REQUIRED: dict[ContractType, str] = {
    ContractType.credit_brl: "initial_amount_brl",
    ContractType.credit_shared: "initial_amount_brl",
    ContractType.hour_bank: "initial_hours",
    ContractType.service_count: "initial_service_count",
    ContractType.closed_value: "initial_amount_brl",
    ContractType.saas_product: "initial_amount_brl",
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: NewContract) -> Contract:
        if data.ends_on <= data.starts_on:
            raise ContractValidationError("ends_on deve ser > starts_on")
        if data.billing_period_months < 1 or data.closing_period_months < 1:
            raise ContractValidationError("períodos devem ser >= 1 mês")
        if (data.closing_period_months % data.billing_period_months != 0
                and data.billing_period_months % data.closing_period_months != 0):
            raise ContractValidationError(
                "ciclos de faturamento e fechamento devem ser múltiplos")
        required = _REQUIRED[data.type]
        if getattr(data, required) in (None, 0):
            raise ContractValidationError(
                f"contrato {data.type} exige {required}")
        # tenant uniqueness of code (RLS already scopes the SELECT to tenant)
        dup = await self.session.execute(
            select(Contract.id).where(Contract.code == data.code)
        )
        if dup.first() is not None:
            raise ContractValidationError(
                f"código {data.code} já existe neste tenant")

        tenant_id = await self._current_tenant_id()
        contract = Contract(
            tenant_id=tenant_id,
            code=data.code,
            type=data.type,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            initial_amount_brl=data.initial_amount_brl,
            initial_hours=data.initial_hours,
            initial_service_count=data.initial_service_count,
            unit_price_brl=data.unit_price_brl,
            travel_franchise_count=data.travel_franchise_count,
            billing_period_months=data.billing_period_months,
            closing_period_months=data.closing_period_months,
            billing_in_advance=data.billing_in_advance,
            accumulate_balance_between_cycles=data.accumulate_balance_between_cycles,
            created_by=data.created_by,
        )
        self.session.add(contract)
        await self.session.flush()
        return contract

    async def _current_tenant_id(self) -> uuid.UUID:
        # H9: imports hoisted to module top (ruff PLC0415-safe).
        res = await self.session.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        )
        val = res.scalar_one()
        if not val:
            raise ContractValidationError("sessão sem tenant (GUC ausente)")
        return uuid.UUID(val)
```

- [ ] **Step 4: Run service test — expect pass; full gate green.**

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/domain apps/sidecar/tests/test_contract_service.py
git commit -m "feat(sidecar): ContractService — criação e validação dos 6 tipos de contrato"
```

---

## Task 10: Consumption service — idempotent append-only + balance

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/consumption_service.py`
- Create: `apps/sidecar/tests/test_consumption_service.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import uuid
import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_record_idempotent_and_balance(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        contract = await ContractService(s).create(NewContract(
            code="HB", type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
            initial_hours=10, unit_price_brl=200, created_by="w"))
        cons = ConsumptionService(s)
        wid = uuid.uuid4()
        ev1 = await cons.record(RecordConsumption(
            contract_id=contract.id, occurred_at=dt.datetime(2026, 1, 5, tzinfo=dt.UTC),
            source_kind="ticket_work", source_ref="znuny:article:1",
            billable_minutes=120, recorded_by="tec", webhook_event_id=wid))
        ev2 = await cons.record(RecordConsumption(
            contract_id=contract.id, occurred_at=dt.datetime(2026, 1, 5, tzinfo=dt.UTC),
            source_kind="ticket_work", source_ref="znuny:article:1",
            billable_minutes=120, recorded_by="tec", webhook_event_id=wid))
        assert ev1.id == ev2.id  # idempotent: same webhook id → same row
        bal = await cons.balance(contract.id)
        # hour_bank: 10h - 120min(2h) = 8h remaining
        assert bal.kind == "hours" and float(bal.remaining) == 8.0
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement `domain/consumption_service.py`**

```python
"""Idempotent append-only consumption recording + per-type balance."""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ConsumptionError
from gerti_sidecar.models import Contract, ConsumptionEvent
from gerti_sidecar.models.enums import ContractType


@dataclasses.dataclass(slots=True)
class RecordConsumption:
    contract_id: uuid.UUID
    occurred_at: dt.datetime
    source_kind: str
    source_ref: str
    billable_minutes: float
    recorded_by: str
    webhook_event_id: uuid.UUID | None = None
    billable_amount_brl: float = 0.0
    service_id: uuid.UUID | None = None


@dataclasses.dataclass(slots=True)
class Balance:
    kind: str  # "hours" | "brl" | "services" | "n/a"
    remaining: float | None


class ConsumptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, data: RecordConsumption) -> ConsumptionEvent:
        if data.billable_minutes < 0:
            raise ConsumptionError("billable_minutes não pode ser negativo")
        if data.webhook_event_id is not None:
            existing = await self.session.execute(
                select(ConsumptionEvent).where(
                    ConsumptionEvent.webhook_event_id == data.webhook_event_id
                )
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                return row  # idempotent: do not double-count
        contract = await self.session.get(Contract, data.contract_id)
        if contract is None:
            raise ConsumptionError("contrato inexistente neste tenant")
        ev = ConsumptionEvent(
            contract_id=data.contract_id,
            occurred_at=data.occurred_at,
            source_kind=data.source_kind,
            source_ref=data.source_ref,
            service_id=data.service_id,
            billable_minutes=data.billable_minutes,
            billable_amount_brl=data.billable_amount_brl,
            unit_price_at_event=contract.unit_price_brl,
            recorded_by=data.recorded_by,
            webhook_event_id=data.webhook_event_id,
        )
        self.session.add(ev)
        await self.session.flush()
        return ev

    async def balance(self, contract_id: uuid.UUID) -> Balance:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ConsumptionError("contrato inexistente neste tenant")
        # glosa_id IS NULL → not written off (glosa lifecycle handled in cycle svc)
        consumed_min = await self.session.scalar(
            select(func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0)).where(
                ConsumptionEvent.contract_id == contract_id,
                ConsumptionEvent.glosa_id.is_(None),
            )
        )
        consumed_brl = await self.session.scalar(
            select(func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)).where(
                ConsumptionEvent.contract_id == contract_id,
                ConsumptionEvent.glosa_id.is_(None),
            )
        )
        consumed_count = await self.session.scalar(
            select(func.count()).where(
                ConsumptionEvent.contract_id == contract_id,
                ConsumptionEvent.glosa_id.is_(None),
                ConsumptionEvent.source_kind == "service_item",
            )
        )
        if contract.type == ContractType.hour_bank:
            initial = float(contract.initial_hours or 0)
            return Balance("hours", initial - float(consumed_min) / 60.0)
        if contract.type in (ContractType.credit_brl, ContractType.credit_shared):
            initial = float(contract.initial_amount_brl or 0)
            return Balance("brl", initial - float(consumed_brl))
        if contract.type == ContractType.service_count:
            initial = float(contract.initial_service_count or 0)
            return Balance("services", initial - float(consumed_count))
        return Balance("n/a", None)  # closed_value / saas_product: no running balance
```

- [ ] **Step 4: Run service test — expect pass; full gate green.**

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/domain/consumption_service.py apps/sidecar/tests/test_consumption_service.py
git commit -m "feat(sidecar): ConsumptionService — registro idempotente append-only + saldo por tipo"
```

---

## Task 11: Cycle closing service — billing≠closing, overage, accrual, glosa

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/cycle_service.py`
- Create: `apps/sidecar/tests/test_cycle_service.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import uuid
import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


@pytest.mark.asyncio
async def test_close_cycle_overage_and_accrual(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(NewContract(
            code="HB", type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
            initial_hours=2, unit_price_brl=150,
            billing_period_months=1, closing_period_months=1,
            accumulate_balance_between_cycles=False, created_by="w"))
        cyc = ContractCycle(contract_id=c.id, kind=CycleKind.closing,
                            period_start=dt.date(2026, 1, 1),
                            period_end=dt.date(2026, 1, 31))
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        await cons.record(RecordConsumption(
            contract_id=c.id, occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
            source_kind="ticket_work", source_ref="a:1",
            billable_minutes=180, recorded_by="t", webhook_event_id=uuid.uuid4()))
        totals = await CycleService(s).close(cyc.id)
        # consumed 3h, franchise/initial 2h → 1h overage * 150 = 150
        assert totals["consumed_minutes"] == 180
        assert totals["overage_minutes"] == 60
        assert float(totals["overage_amount_brl"]) == 150.0
        assert totals["carry_over"] == 0  # accrual disabled
        refreshed = await s.get(ContractCycle, cyc.id)
        assert refreshed.status == CycleStatus.closed and refreshed.closed_at is not None
        # consumption events stamped with this closing cycle
        from gerti_sidecar.models import ConsumptionEvent
        from sqlalchemy import select, func
        n = await s.scalar(select(func.count()).where(
            ConsumptionEvent.closing_cycle_id == cyc.id))
        assert n == 1
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement `domain/cycle_service.py`**

```python
"""Close a closing-cycle: compute consumption, overage, accrual, glosa, snapshot."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import CycleError
from gerti_sidecar.models import Contract, ConsumptionEvent, ContractCycle, Glosa
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus, GlosaStatus


class CycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def close(self, cycle_id: uuid.UUID) -> dict:
        cycle = await self.session.get(ContractCycle, cycle_id)
        if cycle is None:
            raise CycleError("ciclo inexistente neste tenant")
        if cycle.kind != CycleKind.closing:
            raise CycleError("apenas ciclos de fechamento podem ser fechados")
        if cycle.status != CycleStatus.open:
            raise CycleError(f"ciclo não está aberto (status={cycle.status})")
        contract = await self.session.get(Contract, cycle.contract_id)
        if contract is None:
            raise CycleError("contrato do ciclo inexistente")

        start = dt.datetime.combine(cycle.period_start, dt.time.min, tzinfo=dt.UTC)
        end = dt.datetime.combine(cycle.period_end, dt.time.max, tzinfo=dt.UTC)

        # Events in window, not yet assigned a closing cycle, and not
        # written-off by an APPROVED glosa (pending/rejected still count).
        approved_sub = (
            select(Glosa.consumption_event_id)
            .where(Glosa.status == GlosaStatus.approved)
            .scalar_subquery()
        )
        rows = (await self.session.execute(
            select(ConsumptionEvent).where(
                ConsumptionEvent.contract_id == contract.id,
                ConsumptionEvent.closing_cycle_id.is_(None),
                ConsumptionEvent.occurred_at >= start,
                ConsumptionEvent.occurred_at <= end,
                ConsumptionEvent.id.not_in(approved_sub),
            )
        )).scalars().all()

        consumed_minutes = sum(float(r.billable_minutes) for r in rows)
        consumed_brl = sum(float(r.billable_amount_brl) for r in rows)

        franchise_minutes = float(contract.initial_hours or 0) * 60.0 \
            if contract.type == ContractType.hour_bank else 0.0
        overage_minutes = max(0.0, consumed_minutes - franchise_minutes)
        unit = float(contract.unit_price_brl or 0)
        overage_amount = (overage_minutes / 60.0) * unit \
            if contract.type == ContractType.hour_bank else 0.0

        if contract.accumulate_balance_between_cycles:
            carry_over = max(0.0, franchise_minutes - consumed_minutes)
        else:
            carry_over = 0.0

        totals = {
            "consumed_minutes": consumed_minutes,
            "consumed_brl": consumed_brl,
            "franchise_minutes": franchise_minutes,
            "overage_minutes": overage_minutes,
            "overage_amount_brl": overage_amount,
            "carry_over": carry_over,
            "event_count": len(rows),
        }

        await self.session.execute(
            update(ConsumptionEvent)
            .where(ConsumptionEvent.id.in_([r.id for r in rows]))
            .values(closing_cycle_id=cycle.id)
        )
        cycle.status = CycleStatus.closed
        cycle.closed_at = dt.datetime.now(dt.UTC)  # H5: Python value, not func.now()
        cycle.totals = totals
        await self.session.flush()
        return totals
```

- [ ] **Step 4: Run service test — expect pass; full gate green.**

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/domain/cycle_service.py apps/sidecar/tests/test_cycle_service.py
git commit -m "feat(sidecar): CycleService — fechamento (excedente, acúmulo opcional, glosa, snapshot)"
```

---

## Task 12: Adjustment + renewal service

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/adjustment_service.py`
- Create: `apps/sidecar/tests/test_adjustment_service.py`

- [ ] **Step 1: Failing test**

```python
import datetime as dt
import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.adjustment_service import AdjustmentService
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.models import ContractAdjustmentRule, ContractRenewalPolicy
from gerti_sidecar.models.enums import ContractStatus, ContractType


@pytest.mark.asyncio
async def test_apply_index_and_renew(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(NewContract(
            code="C", type=ContractType.credit_brl,
            starts_on=dt.date(2025, 1, 1), ends_on=dt.date(2026, 1, 1),
            initial_amount_brl=1000, unit_price_brl=100, created_by="w"))
        s.add(ContractAdjustmentRule(contract_id=c.id, index_code="IPCA",
              cadence_months=12, next_run_on=dt.date(2026, 1, 1)))
        s.add(ContractRenewalPolicy(contract_id=c.id, auto_renew=True,
              notice_days=30, next_review_on=dt.date(2025, 12, 1),
              renewal_term_months=12))
        await s.flush()
        adj = AdjustmentService(s)
        new_price = await adj.apply_adjustment(c.id, percent=10.0,
                                               on_date=dt.date(2026, 1, 1))
        assert float(new_price) == 110.0  # 100 + 10%
        rule = await s.get(ContractAdjustmentRule, c.id)
        assert rule.last_applied_percent == 10 and rule.next_run_on == dt.date(2027, 1, 1)

        renewed = await adj.renew(c.id, on_date=dt.date(2025, 12, 1))
        assert renewed.ends_on == dt.date(2027, 1, 1)  # +12 months
        assert renewed.status == ContractStatus.active
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement `domain/adjustment_service.py`**

```python
"""Index adjustment (reajuste) + automatic renewal."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import Contract, ContractAdjustmentRule, ContractRenewalPolicy


def _add_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # clamp day to month length (28 is safe for contract anniversaries)
    day = min(d.day, 28)
    return dt.date(year, month, day)


class AdjustmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def apply_adjustment(
        self, contract_id: uuid.UUID, *, percent: float, on_date: dt.date
    ) -> float:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ContractValidationError("contrato inexistente neste tenant")
        rule = await self.session.get(ContractAdjustmentRule, contract_id)
        if rule is None:
            raise ContractValidationError("contrato sem regra de reajuste")
        if rule.cap_percent is not None and percent > float(rule.cap_percent):
            percent = float(rule.cap_percent)  # honor the cap
        base = float(contract.unit_price_brl or 0)
        new_price = round(base * (1 + percent / 100.0), 2)
        contract.unit_price_brl = new_price
        rule.last_applied_on = on_date
        rule.last_applied_percent = percent
        rule.next_run_on = _add_months(on_date, rule.cadence_months)
        await self.session.flush()
        return new_price

    async def renew(self, contract_id: uuid.UUID, *, on_date: dt.date) -> Contract:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ContractValidationError("contrato inexistente neste tenant")
        policy = await self.session.get(ContractRenewalPolicy, contract_id)
        if policy is None or not policy.auto_renew:
            raise ContractValidationError("contrato sem renovação automática")
        term = policy.renewal_term_months or 12
        contract.ends_on = _add_months(contract.ends_on, term)
        contract.status = contract.status.__class__.active
        policy.next_review_on = _add_months(on_date, term)
        await self.session.flush()
        return contract
```

- [ ] **Step 4: Run service test — expect pass; full gate green.**

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/src/gerti_sidecar/domain/adjustment_service.py apps/sidecar/tests/test_adjustment_service.py
git commit -m "feat(sidecar): AdjustmentService — reajuste por índice (com teto) e renovação"
```

---

## Task 13: Balance materialized view + end-to-end test + demo script

**Files:**
- Create: `apps/sidecar/alembic/versions/0009_balance_view.py`
- Create: `apps/sidecar/tests/test_contract_domain_e2e.py`
- Create: `apps/sidecar/scripts/demo_contract.py`

- [ ] **Step 1: Migration `0009_balance_view.py`**

`revision="0009_balance_view"`, `down_revision="0008_policy_ticketlink"`. Use `op.execute` with the **EXACT** Spec #0 §4 DDL (do not paraphrase — the glosa-rejected `FILTER` matters; a contract written-off then `rejected` must count again):

```python
op.execute(
    """
    CREATE MATERIALIZED VIEW gerti.contract_balance_current AS
    SELECT
      c.id AS contract_id,
      c.type,
      CASE c.type
        WHEN 'credit_brl' THEN
          c.initial_amount_brl - COALESCE(SUM(ce.billable_amount_brl) FILTER (
            WHERE ce.glosa_id IS NULL OR EXISTS (
              SELECT 1 FROM gerti.glosa g
              WHERE g.id = ce.glosa_id AND g.status = 'rejected')), 0)
        WHEN 'hour_bank' THEN
          c.initial_hours - COALESCE(SUM(ce.billable_minutes) FILTER (
            WHERE ce.glosa_id IS NULL OR EXISTS (
              SELECT 1 FROM gerti.glosa g
              WHERE g.id = ce.glosa_id AND g.status = 'rejected')), 0) / 60.0
        WHEN 'service_count' THEN
          c.initial_service_count - COALESCE(COUNT(ce.*) FILTER (
            WHERE ce.source_kind = 'service_item'), 0)
        ELSE NULL
      END AS remaining
    FROM gerti.contract c
    LEFT JOIN gerti.consumption_event ce ON ce.contract_id = c.id
    GROUP BY c.id;
    """
)
op.execute(
    "CREATE UNIQUE INDEX ix_contract_balance_current_contract_id "
    "ON gerti.contract_balance_current (contract_id)"
)
op.execute("GRANT SELECT ON gerti.contract_balance_current TO gerti_app")
```

> **RLS BYPASS — KNOWN & ACCEPTED:** Postgres materialized views are NOT row-level-security filtered (RLS applies to base tables, not the matview's stored rows). `gerti.contract_balance_current` therefore exposes ALL tenants' balances to anyone with `SELECT`. Mitigation baked into the design: (1) it is **reporting/refresh-job only**, never queried on a tenant-facing path; (2) tenant-facing balance is served exclusively by `ConsumptionService.balance()` which runs under the tenant GUC against RLS'd base tables; (3) the matview is documented here and in `INTEGRATION.md` as admin-scope. Do NOT add a tenant-scoped query against this matview anywhere. `downgrade()`: `DROP INDEX` then `DROP MATERIALIZED VIEW gerti.contract_balance_current`.

- [ ] **Step 2: End-to-end test**

Create `apps/sidecar/tests/test_contract_domain_e2e.py`:

```python
"""Full lifecycle under RLS as the unprivileged role: create→consume→close→adjust."""
from __future__ import annotations

import datetime as dt
import uuid
import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.adjustment_service import AdjustmentService
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ContractAdjustmentRule, ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind


@pytest.mark.asyncio
async def test_full_contract_lifecycle(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(NewContract(
            code="MSP-OURO", type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
            initial_hours=4, unit_price_brl=160,
            billing_period_months=1, closing_period_months=1, created_by="william"))
        s.add(ContractAdjustmentRule(contract_id=c.id, index_code="IPCA",
              cadence_months=12, next_run_on=dt.date(2027, 1, 1)))
        cyc = ContractCycle(contract_id=c.id, kind=CycleKind.closing,
                            period_start=dt.date(2026, 1, 1),
                            period_end=dt.date(2026, 1, 31))
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        for mins in (90, 120, 150):  # 360 min = 6h, franchise 4h → 2h overage
            await cons.record(RecordConsumption(
                contract_id=c.id, occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
                source_kind="ticket_work", source_ref=f"a:{mins}",
                billable_minutes=mins, recorded_by="tec",
                webhook_event_id=uuid.uuid4()))
        bal = await cons.balance(c.id)
        assert bal.kind == "hours" and float(bal.remaining) == -2.0  # 4h - 6h
        totals = await CycleService(s).close(cyc.id)
        assert totals["overage_minutes"] == 120
        assert float(totals["overage_amount_brl"]) == 320.0  # 2h * 160
        new_price = await AdjustmentService(s).apply_adjustment(
            c.id, percent=8.0, on_date=dt.date(2026, 12, 31))
        assert float(new_price) == 172.8  # 160 + 8%

    # tenant B cannot see tenant A's contract at all (RLS, unprivileged role)
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        rows = (await s.execute(select(Contract.code))).scalars().all()
        assert "MSP-OURO" not in rows
```

(Add `from sqlalchemy import select` and `from gerti_sidecar.models import Contract` to the test's top-level imports — H11: no inline imports, no dead `_session_contracts`/`hasattr` probe.)

- [ ] **Step 3: Demo script (domain-level, no HTTP)**

Create `apps/sidecar/scripts/demo_contract.py`:

```python
"""Domain demo: prints a full MSP contract lifecycle. No HTTP, no Znuny.

Run (needs a Postgres reachable + migrations applied):
  cd apps/sidecar
  DATABASE_URL=postgresql+asyncpg://gerti_sidecar:dev_change_me@<host>:5432/gerti \
    uv run python scripts/demo_contract.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind


async def main() -> None:
    admin_url = os.environ["DATABASE_URL"]  # gerti_sidecar works for app ops
    engine = create_async_engine(admin_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # NOTE: tenant seeding requires an admin (BYPASSRLS) connection in real
    # runs; for the demo assume a tenant already exists or seed via psql.
    # Here we just demonstrate the domain services under a tenant GUC.
    tenant_id = uuid.UUID(os.environ["DEMO_TENANT_ID"])

    async with db.tenant_session_scope(tenant_id, factory=factory) as s:
        c = await ContractService(s).create(NewContract(
            code=f"DEMO-{uuid.uuid4().hex[:6]}", type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
            initial_hours=8, unit_price_brl=180,
            billing_period_months=1, closing_period_months=1, created_by="demo"))
        print(f"Contrato criado: {c.code} ({c.type}) saldo inicial 8h")
        cyc = ContractCycle(contract_id=c.id, kind=CycleKind.closing,
                            period_start=dt.date(2026, 1, 1),
                            period_end=dt.date(2026, 1, 31))
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        for mins in (120, 240, 180):
            await cons.record(RecordConsumption(
                contract_id=c.id, occurred_at=dt.datetime(2026, 1, 9, tzinfo=dt.UTC),
                source_kind="ticket_work", source_ref="demo",
                billable_minutes=mins, recorded_by="tec",
                webhook_event_id=uuid.uuid4()))
        bal = await cons.balance(c.id)
        print(f"Após 9h apontadas → saldo {bal.remaining:.1f}h ({bal.kind})")
        totals = await CycleService(s).close(cyc.id)
        print(f"Ciclo fechado: excedente {totals['overage_minutes']/60:.1f}h "
              f"= R$ {float(totals['overage_amount_brl']):.2f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run e2e test — expect pass; full gate green.**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_contract_domain_e2e.py -q` → 1 passed. Then full gate (`ruff check . && ruff format --check . && mypy src && pytest -q`) — all green. (The demo script is not executed by the gate; just `python -m py_compile scripts/demo_contract.py` to confirm it parses.)

- [ ] **Step 5: Commit**

```bash
cd /home/will/projetos/ground-control
git add apps/sidecar/alembic/versions/0009_balance_view.py apps/sidecar/tests/test_contract_domain_e2e.py apps/sidecar/scripts/demo_contract.py
git commit -m "feat(sidecar): matview de saldo + e2e do domínio de contratos + demo script"
```

---

## Self-Review (controller checklist — done before handing off)

**1. Spec coverage (Spec #0 §4):** contract ✅(T3) · contract_billing_party ✅(T3) · service_catalog_item ✅(T5) · shared_credit_pool ✅(T5) · contract_scope_service/ci ✅(T5) · contract_cycle ✅(T6) · consumption_event append-only+idempotency ✅(T6/T10) · glosa ✅(T6, applied in T11 closing) · contract_adjustment_rule ✅(T7/T12) · contract_renewal_policy ✅(T7/T12) · ticket_contract_link ✅(T7) · contract_balance_current matview ✅(T13) · 6 contract types ✅(T9) · billing≠closing + overage + optional accrual ✅(T11) · per-tenant RLS template ✅(T3, reused T5/T6/T7) · GUC session seam + FORCE on gerti.tenant + fail-closed negative test ✅(T1/T4). Out of scope by design: HTTP APIs (#1E), webhooks-from-Znuny ingestion (#1E), audit_log hash-chain (deferred — note below), v_znuny_* read views (#1E/repository layer). **Gap noted:** Spec #0 `audit_log` is not in #1C — it belongs with the write APIs (#1E); explicitly deferred, not forgotten.

**2. Placeholder scan:** No "TBD/TODO/handle edge cases". Tasks 5/6/7/13 describe migration SQL in prose where the table-shape mirrors models already shown verbatim and the RLS helper is explicitly "paste verbatim from Task 3" — acceptable per DRY (the canonical code IS in Task 3); each such task still names exact columns/policies/indexes and the FK-safe downgrade. Not a placeholder (no missing decisions), but the implementer must transcribe model columns into `sa.Column` — flagged in each task.

**3. Type consistency:** enum names (`ContractType` etc.) and PG type names (`gerti.contract_type` etc.) consistent T2↔T3↔T6↔T7. `tenant_session_scope(tenant_id, *, factory=None)` / `get_tenant_session(request)` signatures consistent T1↔T8↔T9. `NewContract`/`RecordConsumption` dataclass fields consistent across T9/T10/T11/T13. `Balance(kind, remaining)` consistent T10↔T13. Repo `model` classvar + `TenantScopedRepository` consistent T8. Migration revision chain `0002→0003→0004→0005→0006→0007→0008→0009` linear and each `down_revision` matches.

**4. Hardening baked in (H1–H11):** see the "CRITICAL HARDENING" table at the top. Summary: H1 native-enum casts in every default; H2 append-only trigger now permits only `closing_cycle_id`/`glosa_id` UPDATE (does not deadlock cycle close); H3 `contract.shared_pool_id` FK created in 0006 not 0005; H4 `consumption_event.id` uses `Identity` (real BIGSERIAL); H5 `closed_at` is a Python datetime; H6 testcontainer = `postgres:18`; H7 every child policy has `WITH CHECK`; H8 `glosa_id` is FK-less by design; H9 imports hoisted; H10 `updated_at` `onupdate`; H11 dead e2e probe removed. Migration chain (audited real head → forward): **`0004_contract_enums`(head) →0005→0006→0007→0008→0009**, each `down_revision` verified linear. T1/T2 ✅ DONE — not re-created.

**5. Out of scope (unchanged):** `audit_log` (#1E), HTTP APIs (#1E), Znuny webhook ingestion (#1E), `v_znuny_*` read views (#1E).

---

Plan hardened against the audited real state and saved to `docs/superpowers/plans/2026-05-17-spec-1c-contract-domain.md`. Deploy plan: `docs/superpowers/plans/2026-05-17-spec-1c-deploy.md`.
