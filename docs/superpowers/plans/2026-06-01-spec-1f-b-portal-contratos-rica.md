# Spec #1F-b — Portal Cliente: Visão de contratos rica (Fatia A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. TDD is mandatory: write the failing test FIRST, run it red, then make it green.

**Goal:** Turn the raw contract list from #1F-a into a **rich, beautiful, 100% READ-ONLY contract view** over the existing #1C domain: extend `/v1/contracts` (+`id`,+`consumed_percent`), add `GET /v1/contracts/{id}` (detail), `GET /v1/contracts/{id}/consumption` (paginated ledger w/ per-event glosa status), `GET /v1/contracts/{id}/series` (dense daily/weekly aggregation), `GET /v1/dashboard` (balances-by-type + low-balance alerts); a Nuxt dashboard + `/contratos/[id]` detail page with **pure-SVG** charts (progress bar, area/line), low-balance alerts, paginated ledger with glosa indicators, cycles timeline, adjustment/renewal, billing parties; and the discreet **"Desenvolvido por WAS Soluções em Tecnologia"** footer. The portal NEVER mutates the contract domain. NOTHING from Spec §9 YAGNI (tickets, service catalog, abrir-chamado, any write/mutation, admin/onboarding, branding UI, OIDC, export, advanced filters, external chart libs, N+1 optimization) is built, scaffolded, or mentioned as a task.

**Architecture:** Extends the #1F-a sidecar (`apps/sidecar`, repo `ground-control`, branch `main`, HEAD `3bef7a3`). Every new endpoint sits behind BOTH `Depends(get_current_session)` (JWT `gsid`, 401 no/invalid cookie or no tenant, 403 cross-tenant) AND `Depends(get_tenant_session)` (opens `tenant_session_scope` → `SET LOCAL app.current_tenant` → RLS). No new tenant-resolution route. A `{id}` not belonging to the session tenant is hidden by RLS → the query returns nothing → **404 `contract_not_found`** (never 403, never 500 — we do not leak cross-tenant existence). The S3 approved-glosa rule lives in **ONE** place: a new READ-ONLY service `apps/sidecar/src/gerti_sidecar/domain/contract_read_service.py` exposing the `not_written_off` predicate plus aggregation/time-series helpers that reuse `ConsumptionService.balance` verbatim; routers NEVER hand-roll the `glosa_id IS NULL OR glosa_id NOT IN (approved)` predicate. We EXTEND `routers/contracts.py` (`/contracts/*`) and ADD `routers/dashboard.py` (`/dashboard`), wired into `main.py` with `prefix=settings.api_v1_prefix` exactly like the existing routers. The Nuxt portal (`apps/portal`, Nuxt 3 SSR) gets server proxy routes under `server/api/portal/` (forwarding cookie + `x-forwarded-host` via `sidecarFetch`), pure-SVG chart components, the rich dashboard `/`, and `/contratos/[id]`. Deploy is **additive**: `docker-compose.yml` portal+sidecar already `profiles:["gerti"]`; rebuild `--no-cache` portal + recreate sidecar on the VPS (`ssh gc`) and verify public via the Cloudflare edge for both `aurora.was.dev.br` and `technova.was.dev.br`. NO migration (this slice creates no table).

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 async, Pydantic v2; pytest + pytest-asyncio + testcontainers (`postgres:18`). Nuxt 3 SSR, Nitro, @nuxt/ui v3, Tailwind v4, Bricolage Grotesque/Hanken Grotesk, Pinia, TypeScript, Vitest + @nuxt/test-utils, pnpm (corepack, `--frozen-lockfile`). Pure-SVG charts (NO external chart lib). Docker Compose (additive `gerti` profile), Cloudflare edge.

---

## AUDIT — REAL CURRENT STATE (2026-06-01, verified by reading the code)

- **Repo:** `ground-control`, branch `main`, HEAD `3bef7a3` (`docs(spec): #1F-b ...`). Working tree only `.playwright-mcp/` untracked. Root compose is `./docker-compose.yml`; `portal` + `sidecar` already exist under `profiles:["gerti"]` (from #1F-a). **No migration is added by this slice.**
- **`ConsumptionService(session).balance(contract_id) -> Balance(kind, remaining)`** (`domain/consumption_service.py:72-119`), `kind ∈ {"hours","brl","services","n/a"}`, verified math per type. The S3 approved-glosa predicate is at lines 81-90: `approved_glosa_ids = select(Glosa.id).where(Glosa.status == GlosaStatus.approved).scalar_subquery()`; `not_written_off = sa.or_(ConsumptionEvent.glosa_id.is_(None), ConsumptionEvent.glosa_id.not_in(approved_glosa_ids))`. **This is the single source of truth for "counts toward balance".**
- **`CycleService.close`** (`domain/cycle_service.py`) writes `contract_cycle.totals` JSONB with EXACT keys: `consumed_minutes, consumed_brl, franchise_minutes, overage_minutes, overage_amount_brl, carry_over, event_count`. The detail endpoint READS `totals` as-is (never recomputes); open cycles have `totals = None`.
- **`AdjustmentService`** (`domain/adjustment_service.py`): `cap_percent` clamp, `_add_months` last-day fix, `auto_renew` gate. Read-only fields exposed by detail.
- **Models (exact fields verified):** `Contract` (`id` uuid, `code, type:ContractType, status:ContractStatus, starts_on, ends_on, initial_amount_brl:Numeric|None, initial_hours:Numeric|None, initial_service_count:Integer|None, unit_price_brl:Numeric|None, travel_franchise_count:int, billing_period_months, closing_period_months, billing_in_advance:bool, accumulate_balance_between_cycles:bool`). `ContractCycle` (`id, contract_id, kind:CycleKind{billing,closing}, period_start, period_end, status:CycleStatus{open,closed,invoiced}, opened_at, closed_at:None|dt, totals:JSONB|None`). `ConsumptionEvent` (`id:BigInteger Identity, contract_id, occurred_at:tz, source_kind, source_ref, service_id, billable_minutes:Numeric, billable_amount_brl:Numeric, unit_price_at_event, glosa_id:uuid|None (NO FK — H8), closing_cycle_id, recorded_by, recorded_at, webhook_event_id`). `Glosa` (`id:uuid, consumption_event_id:BigInteger, status:GlosaStatus{pending,approved,rejected}, reason, ...`). `ContractAdjustmentRule` (PK `contract_id`; `index_code, cadence_months, next_run_on, cap_percent, last_applied_on, last_applied_percent`). `ContractRenewalPolicy` (PK `contract_id`; `auto_renew, notice_days, next_review_on, renewal_term_months`). `ContractBillingParty` (PK `contract_id`; `legal_name, document, fiscal_address:JSONB, payment_method`). `ContractType` = `{closed_value, credit_brl, credit_shared, hour_bank, saas_product, service_count}`.
- **Auth/RLS seams (unchanged, reused):** `auth/session.py::get_current_session` (401 no tenant / no|invalid|expired cookie; 403 `payload["tenant_id"] != str(request.state.tenant.id)`). `db.py::get_tenant_session` → `tenant_session_scope` (RLS-subject GUC); `db.AdminSessionLocal` is the BYPASSRLS subdomain-identity path ONLY (NOT tenant data). New endpoints use both deps, exactly like `routers/contracts.py::list_contracts`.
- **Router idiom:** `APIRouter(prefix="/contracts", tags=["portal"])`, Pydantic `response_model`, `_session_payload = Depends(get_current_session)`, `session = Depends(get_tenant_session)`. Wired in `main.py::create_app` via `app.include_router(<r>.router, prefix=settings.api_v1_prefix)` BEFORE `app.add_middleware(TenantMiddleware)`.
- **conftest.py:** session-scoped `PostgresContainer("postgres:18")` + init SQL; `engine` applies Alembic head; admin `session` (rollback); `app_db_url`/`app_session_factory` = unprivileged `gerti_sidecar` (RLS-subject); autouse `_reset_settings_cache`. **Test-isolation convention (MANDATORY): bind `db.*` with `monkeypatch.setattr(db, "AdminSessionLocal", ...)` / `monkeypatch.setattr(db, "SessionLocal", app_session_factory)` — bare `db.X = ...` global writes leak across tests and break `test_request_with_unknown_subdomain_returns_404`. ALWAYS use `monkeypatch.setattr`.** (`test_contracts_router.py` is the canonical example.)
- **S1 invariant:** `test_rls_contract_tables.py::test_every_gerti_table_has_rls_enabled_and_forced` — this slice adds NO table, so the `expected` set is unchanged and S1 must STAY green.
- **Seeds:** `scripts/seed_demo_contracts.py` (`seed(s)->aurora_id`; Aurora `AURORA`, 6 contracts; `AUR-HORAS-2026` has 3 consumption events [90,120,150 min] + a **pending** Glosa on event #0; `AUR-CREDITO-2026` has adjustment rule [IPCA cap 8%] + renewal policy [auto-renew]; subdomain `aurora`). `scripts/seed_demo_branding.py` (`seed(s)->(aurora_id, technova_id)`; TechNova `TECHNOVA`, subdomain `technova`, 2 contracts `TNV-HORAS-2026`[hour_bank,24h] + `TNV-CREDITO-2026`[credit_brl,12000], each 2 events). REUSE both for tests/e2e.
- **Portal:** `nuxt.config.ts` (@nuxt/ui, @pinia/nuxt, @nuxt/eslint; `~/assets/css/main.css`; ssr true), `shared/branding.ts` (`Branding`+`DEFAULT_BRANDING` neutral `#475569`), `layouts/default.vue` (reads `useState('branding')` from `event.context.branding`, SSR no flash; app shell w/ header+footer), `server/utils/sidecar.ts` (`sidecarFetch` forwards `x-forwarded-host`+cookie — undici forbids overriding `Host`), `server/api/portal/{me,contracts}.get.ts` (proxy idiom), `server/api/auth/{login,logout}.post.ts`, `pages/{login,index}.vue`. Per-tenant brand via `--brand-primary`/`--brand-accent`.
- **Gate baseline (verified):** sidecar `uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=... uv run pytest -q` → **46 passed**. Expected count stated after each sidecar task (monotonic).

---

## Hardening applied

Static-analysis traps found against the audited code + Postgres/Nuxt/SVG/SSR semantics. Each fix is baked into the named task.

| # | Trap | Fix (mandatory) |
|---|---|---|
| H1 | The S3 glosa predicate (`glosa_id IS NULL OR glosa_id NOT IN (approved)`) is footgun-aware (avoids `NULL NOT IN`); re-deriving it inside routers for `counts_toward_balance` / series would duplicate it and risk drift (e.g. dropping the `IS NULL` arm → `NULL NOT IN` silently drops un-glosa'd events). | **Business rule centralized in ONE place:** new READ-ONLY `domain/contract_read_service.py` exposes `not_written_off_predicate()` (identical to `consumption_service.py:87-90`) and ALL aggregation/series helpers; routers import it and NEVER hand-roll the predicate. Balances/`consumed_percent` reuse `ConsumptionService.balance` verbatim. (Tasks 1, 4, 5, 6) |
| H2 | A `{id}` from another tenant is hidden by RLS → `session.get(Contract, id)` returns `None`; a naive `.scalar_one()` or unchecked attribute access raises → **500**, leaking nothing but breaking the spec's clean 404 and risking a stack trace. | Every `{id}` endpoint does `c = await session.get(Contract, id)`; `if c is None: raise HTTPException(404, "contract_not_found")`. Same for consumption/series (resolve the contract first). **404-not-500** for cross-tenant. (Tasks 4, 5, 6) |
| H3 | No write may touch the #1C domain (read-only absolute, §2.1/§9). An accidental `session.add`/`flush`/`commit`/`update`/`ConsumptionService.record` in a new path mutates the ledger. | **Read-only enforced:** new code uses ONLY `select(...)`/`session.get(...)`/`ConsumptionService.balance` (balance does no writes); ZERO `add`/`flush`/`commit`/`INSERT`/`UPDATE`/`DELETE`/`.record(`/`.close(`/`.apply_adjustment(`/`.renew(`. A grep guard step in Task 7 asserts none of these tokens appear in the new router/service files. (Tasks 4, 5, 6, 7) |
| H4 | `page_size` unbounded → patological payload; `page < 1` → negative OFFSET SQL error; `granularity` not in `{day,week}` → silent wrong bucketing. | Pagination clamp: `page = max(1, page)`; `page_size = min(max(1, page_size), 200)` (default 50); FastAPI `Query(ge=1)` for `page`, `Query(ge=1, le=200)` for `page_size` → 422 on garbage, clamp documented. `granularity: Literal["day","week"] = "day"` → 422 on other values. (Tasks 5, 6) |
| H5 | A multi-year contract's dense daily series = thousands of zero-filled buckets → patological payload (R1). | **Series bucket cap:** compute span = `(min(ends_on, today) - starts_on).days + 1`; if `granularity == "day"` and span > 400, force `granularity = "week"`. Then zero-fill densely at the chosen granularity. (Task 6) |
| H6 | SVG charts that read `window`/`document` or generate random ids break SSR (hydration mismatch); brand color hard-coded breaks white-label. | **SVG SSR-safe & brand-var-driven:** components are pure `props → <svg>` with `viewBox`+`preserveAspectRatio` (no width/height from browser), NO `window`/`document`/`Math.random`/`Date.now` in render, deterministic gradient ids from a `:id` prop or `useId()`; fill/stroke use `var(--brand-primary)`/`var(--brand-accent)` (alerts use FIXED semantic colors, never brand — H8). Vitest renders them server-style. (Tasks 8, 9) |
| H7 | Portal browser must never call the sidecar directly; SSR sub-requests behind cloudflared lose the tenant `Host` (undici rewrites `Host` to `sidecar:8001`). | **Portal proxies forward `x-forwarded-host`:** every new read goes through a `server/api/portal/*` route using the existing `sidecarFetch` (forwards `x-forwarded-host` + `cookie`; undici Host caveat already handled). DO NOT add browser→sidecar fetches. 401 from sidecar → SSR redirect to `/login`. (Tasks 10, 11, 12) |
| H8 | A low-balance alert painted with `--brand-primary` reads as brand, not as an alert, in some tenants; the WAS signature painted with brand color competes with white-label. | Alerts use FIXED semantic colors: `warning` = amber, `critical` = red (Nuxt UI `color="warning"`/`"error"` or fixed Tailwind amber/red), NEVER `--brand-primary`. The **WAS footer** is `text-xs`, muted (`text-neutral-400`/low opacity), NEVER `--brand-primary`/`--brand-accent`; a vitest asserts the footer node carries no brand class/style. (Tasks 9, 11, 12) |
| H9 | `db.*` global writes in new tests leak across tests and break `test_request_with_unknown_subdomain_returns_404` (the shared module globals stay mutated). | **monkeypatch.setattr test isolation:** every new sidecar test binds `db.AdminSessionLocal` (admin engine) and `db.SessionLocal` (`app_session_factory`) via `monkeypatch.setattr(db, ...)` — NEVER bare `db.X = ...`. (Tasks 4, 5, 6, 7) |
| H10 | `Numeric` columns come back from SQLAlchemy as `Decimal`; a Pydantic field typed `float` coerces, but raw arithmetic (e.g. `initial - remaining`) mixing `Decimal` and `float` raises `TypeError`. `consumed_percent` math must cast to `float` first. | All money/hours read for arithmetic are `float(...)`-cast before computing `consumed_percent`; response fields are `float | None`; dates `dt.date`, timestamps `dt.datetime` (tz-aware), event id `int`. Mirrors `contracts.py`'s existing `float` Pydantic fields. (Tasks 3, 4, 5, 6) |
| H11 | `consumed_percent` divides by initial; `initial` 0/None → ZeroDivisionError or misleading 0%. Overage would push the bar > 100%. | `_consumed_percent(contract, balance)` in `contract_read_service.py`: returns `None` for `closed_value`/`saas_product` (`kind=="n/a"`) and when initial is 0/None; else `clamp01((initial - remaining) / initial) * 100` saturating in `[0,100]`. ONE helper, reused by list+detail+dashboard. (Tasks 3, 4, 7) |
| H12 | `low_balance_alerts` must alert only saldo-bearing types; thresholds (warning `<20%`, critical `≤0%`) easy to invert; closed_value/saas_product must NEVER alert. | `contract_read_service.low_balance(...)`: skip `kind=="n/a"`; skip when initial 0/None; `remaining_pct = remaining/initial`; `critical` iff `remaining_pct <= 0`, `warning` iff `0 < remaining_pct < 0.20`, else no alert. Tested with the Aurora seed (hour_bank with pending glosa still counts → known remaining). (Task 7) |
| H13 | `consumption_event.glosa_id` has NO FK (H8 of #1C); a JOIN that assumes referential integrity could drop rows, and only the LATEST/relevant glosa status matters per event. | The consumption endpoint LEFT-OUTER-JOINs `Glosa` on `Glosa.id == ConsumptionEvent.glosa_id` (read-only lookup; integrity is app-layer). `glosa` is `{status}` or `null`; `counts_toward_balance = glosa is None or glosa.status != "approved"` — same predicate as `not_written_off`, asserted equivalent in tests. (Task 5) |
| H14 | `git add -A` / committing the whole tree would sweep `.playwright-mcp/` and unrelated files. | Every commit step lists EXACT paths; the plan-commit (final, separate) adds ONLY this one plan file. No `git add -A`. (all tasks) |

---

## Domain & contract invariants (single source of truth — do not diverge)

- **S3 glosa rule (centralized, ONE place — `domain/contract_read_service.py`):**
  ```python
  def not_written_off_predicate():  # identical to ConsumptionService balance() arm
      approved = select(Glosa.id).where(Glosa.status == GlosaStatus.approved).scalar_subquery()
      return sa.or_(ConsumptionEvent.glosa_id.is_(None),
                    ConsumptionEvent.glosa_id.not_in(approved))
  ```
  An event **counts toward balance iff** it has no glosa OR its glosa status `!= approved`. Pending & rejected STILL count. Routers NEVER re-derive this.
- **`consumed_percent` (centralized helper, reused list+detail+dashboard):** `None` for `n/a` / initial 0|None; else `clamp01((initial - remaining)/initial)*100` in `[0,100]`. `initial` = `initial_hours` (hour_bank) | `initial_amount_brl` (credit_brl/credit_shared) | `initial_service_count` (service_count). All cast `float(...)` first (H10).
- **`totals` JSONB keys (read as-is, never recomputed):** `consumed_minutes, consumed_brl, franchise_minutes, overage_minutes, overage_amount_brl, carry_over, event_count`. `null` for open cycles.
- **Cross-tenant `{id}`:** RLS hides the row → `session.get(Contract,id)` is `None` → `404 contract_not_found` (NOT 403, NOT 500). Applies to detail, consumption, series.
- **Names IDENTICAL across all tasks:** `contract_read_service`, `ContractReadService`, `not_written_off_predicate`, `consumed_percent`, `low_balance`, `daily_series`/`series`, `dashboard`, `counts_toward_balance`, `Balance.kind`/`Balance.remaining`, `get_current_session`, `get_tenant_session`, `gsid`.

---

## Sidecar gate (run verbatim where stated)

```
cd /home/will/projetos/ground-control/apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q
```
Baseline: **46 passed**. Each sidecar task keeps it green + **S1 PASS** + `test_request_with_unknown_subdomain_returns_404` PASS. Expected count stated per task (monotonic).

## Portal gate (run verbatim where stated)

```
cd /home/will/projetos/ground-control/apps/portal && corepack pnpm install --frozen-lockfile && corepack pnpm exec nuxt prepare && corepack pnpm lint && corepack pnpm test run && corepack pnpm build
```

---

## Task 1 — `domain/contract_read_service.py`: centralize the S3 glosa rule + read-only helpers (ADR D17)

**Goal:** Create ONE read-only home for the approved-glosa predicate and the derived read helpers (`consumed_percent`, per-event `counts_toward_balance`, dense time-series, low-balance) so NO router ever re-derives the footgun-aware rule (H1). Record the new read-service as ADR **D17**.

**Files:** Create `apps/sidecar/src/gerti_sidecar/domain/contract_read_service.py` · Create `apps/sidecar/tests/test_contract_read_service.py` · Modify `.ia/DECISIONS.md` (append D17).

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_contract_read_service.py`:
  ```python
  """ContractReadService: S3 glosa predicate + consumed_percent + series + low_balance.

  Asserts the centralized rule matches ConsumptionService.balance() and that
  pending/rejected/absent glosas COUNT while approved glosas do NOT. Uses the
  admin session for setup (BYPASSRLS); the service is pure-read.
  """

  from __future__ import annotations

  import datetime as dt

  import pytest

  from gerti_sidecar.domain.consumption_service import ConsumptionService
  from gerti_sidecar.domain.contract_read_service import ContractReadService
  from gerti_sidecar.models import Contract, ConsumptionEvent, Glosa, Tenant, ZnunyInstance
  from gerti_sidecar.models.enums import ContractType, GlosaStatus


  async def _tenant(session) -> Tenant:
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      t = Tenant(legal_name="A", trade_name="A", document="1",
                 znuny_customer_id="A", znuny_instance_id=inst.id, subdomain="a")
      session.add(t)
      await session.flush()
      return t


  @pytest.mark.asyncio
  async def test_consumed_percent_and_glosa_rule_match_balance(session):
      t = await _tenant(session)
      c = Contract(tenant_id=t.id, code="HB", type=ContractType.hour_bank,
                   starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                   initial_hours=10, unit_price_brl=100, created_by="seed")
      session.add(c)
      await session.flush()
      # 60 + 120 + 60 min = 4h consumed if all count.
      evs = []
      for i, m in enumerate((60, 120, 60)):
          ev = ConsumptionEvent(contract_id=c.id,
              occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
              source_kind="ticket_work", source_ref=f"r{i}",
              billable_minutes=m, recorded_by="seed")
          session.add(ev)
          await session.flush()
          evs.append(ev)
      # APPROVED glosa on the 120-min event -> it must NOT count.
      session.add(Glosa(consumption_event_id=evs[1].id, status=GlosaStatus.approved,
                        reason="x", requested_by="seed"))
      # PENDING glosa on the last 60-min event -> it STILL counts.
      session.add(Glosa(consumption_event_id=evs[2].id, status=GlosaStatus.pending,
                        reason="y", requested_by="seed"))
      await session.flush()

      svc = ContractReadService(session)
      bal = await ConsumptionService(session).balance(c.id)
      # remaining = 10h - (60+60)/60 = 8.0  (120-min approved-glosa event excluded)
      assert bal.remaining == pytest.approx(8.0)
      pct = await svc.consumed_percent(c)
      # consumed 2h of 10h -> 20%
      assert pct == pytest.approx(20.0)

  @pytest.mark.asyncio
  async def test_consumed_percent_none_for_closed_and_zero_initial(session):
      t = await _tenant(session)
      cv = Contract(tenant_id=t.id, code="CV", type=ContractType.closed_value,
                    starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                    initial_amount_brl=9000, unit_price_brl=9000, created_by="seed")
      hb0 = Contract(tenant_id=t.id, code="HB0", type=ContractType.hour_bank,
                     starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                     initial_hours=0, unit_price_brl=100, created_by="seed")
      session.add_all([cv, hb0])
      await session.flush()
      assert await ContractReadService(session).consumed_percent(cv) is None
      assert await ContractReadService(session).consumed_percent(hb0) is None
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contract_read_service.py` → `ModuleNotFoundError: ...contract_read_service`.
- [ ] **Step 3 — Implement the read service.** Create `apps/sidecar/src/gerti_sidecar/domain/contract_read_service.py`:
  ```python
  """Read-only views over the #1C contract domain for the portal (#1F-b).

  ZERO writes: only select(...)/session.get(...) and ConsumptionService.balance.
  The S3 approved-glosa rule lives HERE (and in ConsumptionService.balance) and
  NOWHERE else — routers must reuse not_written_off_predicate() instead of
  re-deriving it (avoids the `NULL NOT IN (..)` footgun).
  """

  from __future__ import annotations

  import datetime as dt
  import uuid
  from dataclasses import dataclass

  import sqlalchemy as sa
  from sqlalchemy import func, select
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy.sql.elements import ColumnElement

  from gerti_sidecar.domain.consumption_service import Balance, ConsumptionService
  from gerti_sidecar.models import ConsumptionEvent, Contract, Glosa
  from gerti_sidecar.models.enums import ContractType, GlosaStatus


  def not_written_off_predicate() -> ColumnElement[bool]:
      """The S3 rule: event counts toward balance iff no glosa OR glosa != approved.

      IDENTICAL to ConsumptionService.balance() (consumption_service.py). The
      explicit `glosa_id IS NULL` arm avoids SQL `NULL NOT IN (..)` = NULL, which
      would WRONGLY drop un-glosa'd events.
      """
      approved = select(Glosa.id).where(Glosa.status == GlosaStatus.approved).scalar_subquery()
      return sa.or_(
          ConsumptionEvent.glosa_id.is_(None),
          ConsumptionEvent.glosa_id.not_in(approved),
      )


  def _initial_for(contract: Contract) -> float | None:
      if contract.type == ContractType.hour_bank:
          return float(contract.initial_hours) if contract.initial_hours is not None else None
      if contract.type in (ContractType.credit_brl, ContractType.credit_shared):
          return (
              float(contract.initial_amount_brl)
              if contract.initial_amount_brl is not None
              else None
          )
      if contract.type == ContractType.service_count:
          return (
              float(contract.initial_service_count)
              if contract.initial_service_count is not None
              else None
          )
      return None  # closed_value / saas_product: no running balance


  def consumed_percent_from(contract: Contract, balance: Balance) -> float | None:
      """clamp01((initial - remaining)/initial)*100; None for n/a or 0/absent base."""
      if balance.remaining is None:
          return None
      initial = _initial_for(contract)
      if initial is None or initial == 0:
          return None
      pct = (initial - float(balance.remaining)) / initial * 100.0
      return max(0.0, min(100.0, pct))


  @dataclass(slots=True)
  class SeriesPoint:
      bucket: dt.date
      value: float


  @dataclass(slots=True)
  class Series:
      granularity: str  # "day" | "week"
      kind: str         # "hours" | "brl" | "services" | "n/a"
      points: list[SeriesPoint]


  @dataclass(slots=True)
  class LowBalanceAlert:
      contract_id: uuid.UUID
      code: str
      type: str
      kind: str
      remaining: float
      consumed_percent: float | None
      severity: str  # "warning" | "critical"


  class ContractReadService:
      def __init__(self, session: AsyncSession) -> None:
          self.session = session
          self._cons = ConsumptionService(session)

      async def consumed_percent(self, contract: Contract) -> float | None:
          bal = await self._cons.balance(contract.id)
          return consumed_percent_from(contract, bal)

      async def series(
          self, contract: Contract, *, granularity: str = "day", today: dt.date | None = None
      ) -> Series:
          """Dense (zero-filled) consumption series within the contract window.

          Window = starts_on .. min(ends_on, today). >400 daily buckets forces week
          (H5). Metric per kind; glosa-approved events excluded (S3, centralized).
          """
          today = today or dt.datetime.now(dt.UTC).date()
          end = min(contract.ends_on, today)
          start = contract.starts_on
          if end < start:
              end = start
          span_days = (end - start).days + 1
          if granularity == "day" and span_days > 400:
              granularity = "week"

          bal_kind = (await self._cons.balance(contract.id)).kind

          if bal_kind == "hours":
              value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0) / 60.0
              extra: list[ColumnElement[bool]] = []
          elif bal_kind == "brl":
              value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)
              extra = []
          elif bal_kind == "services":
              value_expr = func.count()
              extra = [ConsumptionEvent.source_kind == "service_item"]
          else:  # n/a -> empty/zeros
              return Series(granularity=granularity, kind=bal_kind, points=[])

          # bucket key: date(occurred_at) for day; ISO Monday (date_trunc week) for week.
          if granularity == "week":
              bucket_col = func.date_trunc("week", ConsumptionEvent.occurred_at)
          else:
              bucket_col = func.cast(ConsumptionEvent.occurred_at, sa.Date)
          rows = (
              await self.session.execute(
                  select(bucket_col.label("b"), value_expr.label("v"))
                  .where(
                      ConsumptionEvent.contract_id == contract.id,
                      not_written_off_predicate(),
                      *extra,
                  )
                  .group_by(bucket_col)
              )
          ).all()
          by_bucket: dict[dt.date, float] = {}
          for b, v in rows:
              key = b.date() if isinstance(b, dt.datetime) else b
              by_bucket[key] = float(v or 0.0)

          points: list[SeriesPoint] = []
          if granularity == "week":
              cur = start - dt.timedelta(days=start.weekday())  # ISO Monday
              while cur <= end:
                  points.append(SeriesPoint(bucket=cur, value=by_bucket.get(cur, 0.0)))
                  cur = cur + dt.timedelta(days=7)
          else:
              cur = start
              while cur <= end:
                  points.append(SeriesPoint(bucket=cur, value=by_bucket.get(cur, 0.0)))
                  cur = cur + dt.timedelta(days=1)
          return Series(granularity=granularity, kind=bal_kind, points=points)

      async def low_balance(self, contract: Contract) -> LowBalanceAlert | None:
          """warning when 0 < remaining/initial < 0.20; critical when <= 0.

          Only saldo-bearing types (hour_bank/credit_brl/credit_shared/service_count);
          closed_value/saas_product (kind=='n/a') NEVER alert.
          """
          bal = await self._cons.balance(contract.id)
          if bal.kind == "n/a" or bal.remaining is None:
              return None
          initial = _initial_for(contract)
          if initial is None or initial == 0:
              return None
          remaining_pct = float(bal.remaining) / initial
          if remaining_pct >= 0.20:
              return None
          severity = "critical" if remaining_pct <= 0 else "warning"
          return LowBalanceAlert(
              contract_id=contract.id,
              code=contract.code,
              type=contract.type.value,
              kind=bal.kind,
              remaining=float(bal.remaining),
              consumed_percent=consumed_percent_from(contract, bal),
              severity=severity,
          )
  ```
- [ ] **Step 4 — Run, expect pass.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contract_read_service.py` → 2 passed.
- [ ] **Step 5 — ADR D17.** Append to `.ia/DECISIONS.md` a `## D17 — Read-service do portal (#1F-b): regra S3 da glosa centralizada, leitura pura` section: **Contexto** — a fatia #1F-b precisa de `consumed_percent`, `counts_toward_balance` por evento, série densa e alertas de saldo baixo; a regra S3 (só glosa `approved` remove do saldo, com o braço `IS NULL` anti `NULL NOT IN`) já vive em `ConsumptionService.balance`; reimplementá-la nos routers duplicaria o footgun. **Decisão** — introduzir `domain/contract_read_service.py` (READ-ONLY: só `select`/`session.get`/`ConsumptionService.balance`) com `not_written_off_predicate()` (idêntico ao braço do `balance()`), `consumed_percent_from`, `series` (densa, cap 400→week) e `low_balance` (limiar 20% warning / ≤0 critical, só tipos com saldo). Os routers `/v1/contracts/*` e `/v1/dashboard` consomem este service; NENHUM router redefine a regra. Portal é read-only sobre #1C (nenhum `add`/`flush`/`commit`). **Evidência** — `test_contract_read_service.py` (predicate casa com `balance()`; glosa approved exclui, pending/absent contam; `consumed_percent` None p/ n/a e base 0).
- [ ] **Step 6 — Run the full Sidecar gate.** Expected: **48 passed** (baseline 46 + the 2 new test functions). S1 + unknown-subdomain still PASS.
- [ ] **Step 7 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/domain/contract_read_service.py apps/sidecar/tests/test_contract_read_service.py .ia/DECISIONS.md && git -c commit.gpgsign=false commit -m "feat(#1F-b): contract_read_service (regra S3 centralizada + consumed_percent/series/low_balance) + ADR D17"
  ```

---

## Task 2 — Extend `GET /v1/contracts` (+`id`, +`consumed_percent`), KEEP existing fields

**Goal:** Add `id: uuid` and `consumed_percent: float | None` to each list item without removing/renaming any existing field (§4.2.1). Reuse the centralized helper (no extra query beyond the `balance()` already run).

**Files:** Modify `apps/sidecar/src/gerti_sidecar/routers/contracts.py` · Modify `apps/sidecar/tests/test_contracts_router.py`.

- [ ] **Step 1 — Extend the existing test (failing).** In `tests/test_contracts_router.py`, after the existing `assert rows[0]["saldo"]["remaining"] == 10000.0`, append:
  ```python
        assert rows[0]["id"] == str(c.id)
        # credit_brl with full balance (no consumption) -> 0% consumed
        assert rows[0]["consumed_percent"] == 0.0
  ```
  (`c` is the `Contract` already created/committed in this test; reference it directly.)
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contracts_router.py` → KeyError `id`/`consumed_percent`.
- [ ] **Step 3 — Extend the router.** Modify `apps/sidecar/src/gerti_sidecar/routers/contracts.py`:
  - Add imports: `import uuid` (top) and `from gerti_sidecar.domain.contract_read_service import consumed_percent_from`.
  - Add fields to `ContractItem` (after `saldo: Saldo`):
    ```python
        id: uuid.UUID
        consumed_percent: float | None
    ```
  - In `list_contracts`, inside the loop, after `bal = await cons.balance(c.id)`:
    ```python
            out.append(
                ContractItem(
                    id=c.id,
                    code=c.code,
                    type=c.type.value,
                    status=c.status.value,
                    starts_on=c.starts_on,
                    ends_on=c.ends_on,
                    saldo=Saldo(kind=bal.kind, remaining=bal.remaining),
                    consumed_percent=consumed_percent_from(c, bal),
                )
            )
    ```
    (Replace the existing `out.append(...)` block with this one. Reuses the already-fetched `bal`; no extra query — DRY/YAGNI per §R2.)
- [ ] **Step 4 — Run the full Sidecar gate.** Expected: **48 passed** (no new test FUNCTION; the existing `test_contracts_scoped_and_authed` was extended in place). S1 + unknown-subdomain PASS.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/contracts.py apps/sidecar/tests/test_contracts_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-b): GET /v1/contracts estendido (+id, +consumed_percent) reusando o read-service"
  ```

---

## Task 3 — (shared notes for `{id}` endpoints) — no code

> Tasks 4/5/6 all resolve the contract first via `c = await session.get(Contract, contract_id)` and return `404 contract_not_found` when `None` (RLS hid the cross-tenant row — H2). They all bind `db.AdminSessionLocal`+`db.SessionLocal` via `monkeypatch.setattr` (H9). They all reuse `ContractReadService` / `ConsumptionService.balance` (H1) and never write (H3). This task is a marker only — proceed to Task 4. (Numbered to keep the task list explicit and stable.)

---

## Task 4 — `GET /v1/contracts/{id}` — full detail (contract + saldo + cycles + adjustment + renewal + billing parties)

**Goal:** §4.2.2 detail. `cycles` (billing+closing, `period_start` asc, raw `totals` JSONB or null), `adjustment_rule`/`renewal_policy` (null if absent), `billing_parties` (0..n). 404 cross-tenant.

**Files:** Modify `apps/sidecar/src/gerti_sidecar/routers/contracts.py` · Create `apps/sidecar/tests/test_contract_detail_router.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_contract_detail_router.py`:
  ```python
  """GET /v1/contracts/{id}: detail, cycles totals raw, adjustment/renewal/parties, 404 cross-tenant."""

  from __future__ import annotations

  import datetime as dt

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import (
      Contract, ContractAdjustmentRule, ContractBillingParty, ContractCycle,
      ContractRenewalPolicy, Tenant, TenantBranding, ZnunyInstance,
  )
  from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


  async def _two_tenants_with_contract(session):
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      b = Tenant(legal_name="Tech", trade_name="Tech", document="2",
                 znuny_customer_id="TECH", znuny_instance_id=inst.id, subdomain="technova")
      session.add_all([a, b])
      await session.flush()
      session.add_all([TenantBranding(tenant_id=a.id, display_name="Aurora Móveis"),
                       TenantBranding(tenant_id=b.id, display_name="TechNova")])
      c = Contract(tenant_id=a.id, code="AUR-HB", type=ContractType.hour_bank,
                   starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                   initial_hours=40, unit_price_brl=180, created_by="seed")
      session.add(c)
      await session.flush()
      closed = ContractCycle(contract_id=c.id, kind=CycleKind.closing,
          period_start=dt.date(2026, 1, 1), period_end=dt.date(2026, 1, 31),
          status=CycleStatus.closed, closed_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
          totals={"consumed_minutes": 360.0, "overage_minutes": 0.0, "event_count": 3})
      open_billing = ContractCycle(contract_id=c.id, kind=CycleKind.billing,
          period_start=dt.date(2026, 2, 1), period_end=dt.date(2026, 2, 28),
          status=CycleStatus.open)
      session.add_all([closed, open_billing])
      session.add(ContractAdjustmentRule(contract_id=c.id, index_code="IPCA",
          cadence_months=12, next_run_on=dt.date(2027, 1, 1), cap_percent=8.00))
      session.add(ContractRenewalPolicy(contract_id=c.id, auto_renew=True,
          notice_days=30, next_review_on=dt.date(2026, 11, 30), renewal_term_months=12))
      session.add(ContractBillingParty(contract_id=c.id, legal_name="Aurora SA",
          document="18.472.366/0001-90", fiscal_address={"city": "SP"},
          payment_method="boleto"))
      await session.commit()
      return a, b, c


  @pytest.mark.asyncio
  async def test_detail_full_and_404_cross_tenant(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      a, b, c = await _two_tenants_with_contract(session)
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      ha = {"host": "aurora.suporte.gerti.com.br"}
      ht = {"host": "technova.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          cl.cookies.set("gsid", encode_session(str(a.id), "joe", st))
          r = await cl.get(f"/v1/contracts/{c.id}", headers=ha)
          assert r.status_code == 200
          body = r.json()
          assert body["code"] == "AUR-HB"
          assert body["initial_hours"] == 40.0
          assert body["saldo"]["kind"] == "hours"
          # cycles ordered by period_start asc, both kinds; totals raw on closed, null on open
          assert [cy["kind"] for cy in body["cycles"]] == ["closing", "billing"]
          assert body["cycles"][0]["totals"]["event_count"] == 3
          assert body["cycles"][1]["totals"] is None
          assert body["adjustment_rule"]["index_code"] == "IPCA"
          assert body["adjustment_rule"]["cap_percent"] == 8.0
          assert body["renewal_policy"]["auto_renew"] is True
          assert len(body["billing_parties"]) == 1
          assert body["billing_parties"][0]["payment_method"] == "boleto"
          # cross-tenant: TechNova session asking Aurora's contract id -> 404 (RLS hid it)
          cl.cookies.clear()
          cl.cookies.set("gsid", encode_session(str(b.id), "x", st))
          xr = await cl.get(f"/v1/contracts/{c.id}", headers=ht)
          assert xr.status_code == 404
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contract_detail_router.py` → 404/route missing.
- [ ] **Step 3 — Add the detail endpoint.** In `apps/sidecar/src/gerti_sidecar/routers/contracts.py`:
  - Add imports: `from fastapi import APIRouter, Depends, HTTPException, Path` (extend existing), `from sqlalchemy import select` (exists), and:
    ```python
    from gerti_sidecar.models import (
        Contract,
        ContractAdjustmentRule,
        ContractBillingParty,
        ContractCycle,
        ContractRenewalPolicy,
    )
    ```
    (replace the existing `from gerti_sidecar.models import Contract` line).
  - Add response models (after `ContractItem`):
    ```python
    class CycleItem(BaseModel):
        id: uuid.UUID
        kind: str
        period_start: dt.date
        period_end: dt.date
        status: str
        closed_at: dt.datetime | None
        totals: dict[str, object] | None


    class AdjustmentRuleOut(BaseModel):
        index_code: str
        cadence_months: int
        next_run_on: dt.date
        cap_percent: float | None
        last_applied_on: dt.date | None
        last_applied_percent: float | None


    class RenewalPolicyOut(BaseModel):
        auto_renew: bool
        notice_days: int
        next_review_on: dt.date
        renewal_term_months: int | None


    class BillingPartyOut(BaseModel):
        legal_name: str
        document: str
        fiscal_address: dict[str, object]
        payment_method: str | None


    class ContractDetail(BaseModel):
        id: uuid.UUID
        code: str
        type: str
        status: str
        starts_on: dt.date
        ends_on: dt.date
        initial_amount_brl: float | None
        initial_hours: float | None
        initial_service_count: int | None
        unit_price_brl: float | None
        travel_franchise_count: int
        billing_period_months: int
        closing_period_months: int
        billing_in_advance: bool
        accumulate_balance_between_cycles: bool
        saldo: Saldo
        consumed_percent: float | None
        cycles: list[CycleItem]
        adjustment_rule: AdjustmentRuleOut | None
        renewal_policy: RenewalPolicyOut | None
        billing_parties: list[BillingPartyOut]
    ```
  - Add the endpoint (after `list_contracts`):
    ```python
    @router.get("/{contract_id}", response_model=ContractDetail)
    async def get_contract(
        contract_id: uuid.UUID = Path(...),
        _session_payload: SessionPayload = Depends(get_current_session),
        session: AsyncSession = Depends(get_tenant_session),
    ) -> ContractDetail:
        c = await session.get(Contract, contract_id)
        if c is None:  # RLS hid a cross-tenant row -> 404, never 403/500 (H2)
            raise HTTPException(status_code=404, detail="contract_not_found")
        bal = await ConsumptionService(session).balance(c.id)
        cycles = (
            await session.execute(
                select(ContractCycle)
                .where(ContractCycle.contract_id == c.id)
                .order_by(ContractCycle.period_start.asc())
            )
        ).scalars().all()
        rule = await session.get(ContractAdjustmentRule, c.id)
        policy = await session.get(ContractRenewalPolicy, c.id)
        parties = (
            await session.execute(
                select(ContractBillingParty).where(ContractBillingParty.contract_id == c.id)
            )
        ).scalars().all()
        return ContractDetail(
            id=c.id,
            code=c.code,
            type=c.type.value,
            status=c.status.value,
            starts_on=c.starts_on,
            ends_on=c.ends_on,
            initial_amount_brl=(
                float(c.initial_amount_brl) if c.initial_amount_brl is not None else None
            ),
            initial_hours=float(c.initial_hours) if c.initial_hours is not None else None,
            initial_service_count=c.initial_service_count,
            unit_price_brl=float(c.unit_price_brl) if c.unit_price_brl is not None else None,
            travel_franchise_count=c.travel_franchise_count,
            billing_period_months=c.billing_period_months,
            closing_period_months=c.closing_period_months,
            billing_in_advance=c.billing_in_advance,
            accumulate_balance_between_cycles=c.accumulate_balance_between_cycles,
            saldo=Saldo(kind=bal.kind, remaining=bal.remaining),
            consumed_percent=consumed_percent_from(c, bal),
            cycles=[
                CycleItem(
                    id=cy.id,
                    kind=cy.kind.value,
                    period_start=cy.period_start,
                    period_end=cy.period_end,
                    status=cy.status.value,
                    closed_at=cy.closed_at,
                    totals=cy.totals,
                )
                for cy in cycles
            ],
            adjustment_rule=(
                AdjustmentRuleOut(
                    index_code=rule.index_code,
                    cadence_months=rule.cadence_months,
                    next_run_on=rule.next_run_on,
                    cap_percent=float(rule.cap_percent) if rule.cap_percent is not None else None,
                    last_applied_on=rule.last_applied_on,
                    last_applied_percent=(
                        float(rule.last_applied_percent)
                        if rule.last_applied_percent is not None
                        else None
                    ),
                )
                if rule is not None
                else None
            ),
            renewal_policy=(
                RenewalPolicyOut(
                    auto_renew=policy.auto_renew,
                    notice_days=policy.notice_days,
                    next_review_on=policy.next_review_on,
                    renewal_term_months=policy.renewal_term_months,
                )
                if policy is not None
                else None
            ),
            billing_parties=[
                BillingPartyOut(
                    legal_name=p.legal_name,
                    document=p.document,
                    fiscal_address=p.fiscal_address,
                    payment_method=p.payment_method,
                )
                for p in parties
            ],
        )
    ```
- [ ] **Step 4 — Run the full Sidecar gate.** Expected: **49 passed** (+1 test function). S1 + unknown-subdomain PASS.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/contracts.py apps/sidecar/tests/test_contract_detail_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-b): GET /v1/contracts/{id} detalhe completo (cycles totals raw + reajuste/renovação/partes, 404 cross-tenant)"
  ```

---

## Task 5 — `GET /v1/contracts/{id}/consumption` — paginated ledger w/ per-event glosa + counts_toward_balance

**Goal:** §4.2.3. `?page≥1&page_size` (default 50, clamp ≤200), order `occurred_at DESC, id DESC`, per-event `glosa:{status}|null` + `counts_toward_balance` via the centralized S3 rule, `total` = COUNT in the same RLS window. 404 cross-tenant.

**Files:** Modify `apps/sidecar/src/gerti_sidecar/routers/contracts.py` · Create `apps/sidecar/tests/test_contract_consumption_router.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_contract_consumption_router.py`:
  ```python
  """GET /v1/contracts/{id}/consumption: order, pagination clamp, glosa status, counts_toward_balance, 404."""

  from __future__ import annotations

  import datetime as dt

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import (
      ConsumptionEvent, Contract, Glosa, Tenant, TenantBranding, ZnunyInstance,
  )
  from gerti_sidecar.models.enums import ContractType, GlosaStatus


  @pytest.mark.asyncio
  async def test_consumption_paginated_and_glosa(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(a)
      await session.flush()
      session.add(TenantBranding(tenant_id=a.id, display_name="Aurora Móveis"))
      c = Contract(tenant_id=a.id, code="AUR-HB", type=ContractType.hour_bank,
                   starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                   initial_hours=40, unit_price_brl=180, created_by="seed")
      session.add(c)
      await session.flush()
      evs = []
      for i, m in enumerate((60, 90, 120)):
          ev = ConsumptionEvent(contract_id=c.id,
              occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
              source_kind="ticket_work", source_ref=f"r{i}",
              billable_minutes=m, recorded_by="seed")
          session.add(ev)
          await session.flush()
          evs.append(ev)
      # approved glosa on the FIRST (oldest) event; pending on the second.
      session.add(Glosa(consumption_event_id=evs[0].id, status=GlosaStatus.approved,
                        reason="x", requested_by="seed"))
      session.add(Glosa(consumption_event_id=evs[1].id, status=GlosaStatus.pending,
                        reason="y", requested_by="seed"))
      await session.commit()
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      ha = {"host": "aurora.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          cl.cookies.set("gsid", encode_session(str(a.id), "joe", st))
          # page_size clamp to 200 even if asked higher; total = 3
          r = await cl.get(f"/v1/contracts/{c.id}/consumption?page=1&page_size=500", headers=ha)
          assert r.status_code == 200
          body = r.json()
          assert body["total"] == 3
          assert body["page_size"] == 200
          # order occurred_at DESC -> newest (120-min, r2) first
          assert body["items"][0]["source_ref"] == "r2"
          assert body["items"][0]["glosa"] is None
          assert body["items"][0]["counts_toward_balance"] is True
          # oldest event has approved glosa -> does NOT count
          last = body["items"][-1]
          assert last["source_ref"] == "r0"
          assert last["glosa"]["status"] == "approved"
          assert last["counts_toward_balance"] is False
          # pending glosa STILL counts
          mid = body["items"][1]
          assert mid["glosa"]["status"] == "pending"
          assert mid["counts_toward_balance"] is True
          # paging: page_size 2 -> 2 items, page 2 -> 1 item
          p1 = (await cl.get(f"/v1/contracts/{c.id}/consumption?page=1&page_size=2", headers=ha)).json()
          assert len(p1["items"]) == 2 and p1["page"] == 1
          p2 = (await cl.get(f"/v1/contracts/{c.id}/consumption?page=2&page_size=2", headers=ha)).json()
          assert len(p2["items"]) == 1

  @pytest.mark.asyncio
  async def test_consumption_404_cross_tenant(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      b = Tenant(legal_name="Tech", trade_name="Tech", document="2",
                 znuny_customer_id="TECH", znuny_instance_id=inst.id, subdomain="technova")
      session.add_all([a, b])
      await session.flush()
      session.add_all([TenantBranding(tenant_id=a.id, display_name="A"),
                       TenantBranding(tenant_id=b.id, display_name="T")])
      c = Contract(tenant_id=a.id, code="AUR-HB", type=ContractType.hour_bank,
                   starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                   initial_hours=40, created_by="seed")
      session.add(c)
      await session.commit()
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          cl.cookies.set("gsid", encode_session(str(b.id), "x", st))
          xr = await cl.get(f"/v1/contracts/{c.id}/consumption",
                            headers={"host": "technova.suporte.gerti.com.br"})
          assert xr.status_code == 404
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contract_consumption_router.py` → route missing.
- [ ] **Step 3 — Add the consumption endpoint.** In `apps/sidecar/src/gerti_sidecar/routers/contracts.py`:
  - Extend imports: `from fastapi import APIRouter, Depends, HTTPException, Path, Query`; `from sqlalchemy import func, select`; add `from gerti_sidecar.models import ..., Glosa` (extend the models import list); add `from gerti_sidecar.domain.contract_read_service import consumed_percent_from, not_written_off_predicate`.
  - Add response models:
    ```python
    class GlosaOut(BaseModel):
        status: str


    class ConsumptionItem(BaseModel):
        id: int
        occurred_at: dt.datetime
        source_kind: str
        source_ref: str
        billable_minutes: float
        billable_amount_brl: float
        glosa: GlosaOut | None
        counts_toward_balance: bool


    class ConsumptionPage(BaseModel):
        page: int
        page_size: int
        total: int
        items: list[ConsumptionItem]
    ```
  - Add the endpoint:
    ```python
    @router.get("/{contract_id}/consumption", response_model=ConsumptionPage)
    async def get_consumption(
        contract_id: uuid.UUID = Path(...),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _session_payload: SessionPayload = Depends(get_current_session),
        session: AsyncSession = Depends(get_tenant_session),
    ) -> ConsumptionPage:
        c = await session.get(Contract, contract_id)
        if c is None:  # RLS hid cross-tenant -> 404 (H2)
            raise HTTPException(status_code=404, detail="contract_not_found")
        page = max(1, page)
        page_size = min(max(1, page_size), 200)  # clamp (H4)
        total = await session.scalar(
            select(func.count())
            .select_from(ConsumptionEvent)
            .where(ConsumptionEvent.contract_id == c.id)
        ) or 0
        # LEFT OUTER JOIN Glosa (glosa_id has no FK — H13); status read-only.
        rows = (
            await session.execute(
                select(ConsumptionEvent, Glosa.status)
                .outerjoin(Glosa, Glosa.id == ConsumptionEvent.glosa_id)
                .where(ConsumptionEvent.contract_id == c.id)
                .order_by(ConsumptionEvent.occurred_at.desc(), ConsumptionEvent.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
        items: list[ConsumptionItem] = []
        for ev, glosa_status in rows:
            counts = glosa_status is None or glosa_status != GlosaStatus.approved
            items.append(
                ConsumptionItem(
                    id=ev.id,
                    occurred_at=ev.occurred_at,
                    source_kind=ev.source_kind,
                    source_ref=ev.source_ref,
                    billable_minutes=float(ev.billable_minutes),
                    billable_amount_brl=float(ev.billable_amount_brl),
                    glosa=GlosaOut(status=glosa_status.value) if glosa_status is not None else None,
                    counts_toward_balance=counts,
                )
            )
        return ConsumptionPage(page=page, page_size=page_size, total=int(total), items=items)
    ```
    > **Note:** `counts_toward_balance` here uses the SAME truth as `not_written_off_predicate()` (glosa null OR != approved). The predicate is imported for the SERIES endpoint (Task 6) which aggregates in SQL; the per-row flag mirrors it in Python on the joined status. Tests assert they agree. Do NOT re-derive a different rule.
- [ ] **Step 4 — Run the full Sidecar gate.** Expected: **51 passed** (+2 test functions). S1 + unknown-subdomain PASS.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/contracts.py apps/sidecar/tests/test_contract_consumption_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-b): GET /v1/contracts/{id}/consumption paginado (glosa status + counts_toward_balance via regra S3, clamp 200, 404 cross-tenant)"
  ```

---

## Task 6 — `GET /v1/contracts/{id}/series` — dense daily/weekly aggregation (SVG chart data)

**Goal:** §4.2.4. `?granularity=day|week` (default day); window `starts_on..min(ends_on,today)`; zero-filled dense buckets; cap 400 daily → force week (H5); metric per `kind`; glosa-approved excluded (centralized S3). 404 cross-tenant. Reuses `ContractReadService.series`.

**Files:** Modify `apps/sidecar/src/gerti_sidecar/routers/contracts.py` · Create `apps/sidecar/tests/test_contract_series_router.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_contract_series_router.py`:
  ```python
  """GET /v1/contracts/{id}/series: dense daily, glosa-approved excluded, 404 cross-tenant."""

  from __future__ import annotations

  import datetime as dt

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import (
      ConsumptionEvent, Contract, Glosa, Tenant, TenantBranding, ZnunyInstance,
  )
  from gerti_sidecar.models.enums import ContractType, GlosaStatus


  @pytest.mark.asyncio
  async def test_series_dense_daily_excludes_approved(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(a)
      await session.flush()
      session.add(TenantBranding(tenant_id=a.id, display_name="A"))
      # short window so daily buckets are dense and few
      c = Contract(tenant_id=a.id, code="AUR-HB", type=ContractType.hour_bank,
                   starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 1, 5),
                   initial_hours=40, unit_price_brl=180, created_by="seed")
      session.add(c)
      await session.flush()
      e1 = ConsumptionEvent(contract_id=c.id, occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
          source_kind="ticket_work", source_ref="r1", billable_minutes=60, recorded_by="seed")
      e2 = ConsumptionEvent(contract_id=c.id, occurred_at=dt.datetime(2026, 1, 4, tzinfo=dt.UTC),
          source_kind="ticket_work", source_ref="r2", billable_minutes=120, recorded_by="seed")
      session.add_all([e1, e2])
      await session.flush()
      # approved glosa on e2 -> excluded from series
      session.add(Glosa(consumption_event_id=e2.id, status=GlosaStatus.approved,
                        reason="x", requested_by="seed"))
      await session.commit()
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      ha = {"host": "aurora.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          cl.cookies.set("gsid", encode_session(str(a.id), "joe", st))
          # today after window so end == ends_on -> 5 dense daily buckets Jan 1..5
          r = await cl.get(f"/v1/contracts/{c.id}/series?today=2026-06-01", headers=ha)
          assert r.status_code == 200
          body = r.json()
          assert body["granularity"] == "day"
          assert body["kind"] == "hours"
          assert [p["bucket"] for p in body["points"]] == [
              "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
          # Jan 2 = 60min/60 = 1.0h; Jan 4 excluded (approved glosa) -> 0.0
          assert body["points"][1]["value"] == pytest.approx(1.0)
          assert body["points"][3]["value"] == pytest.approx(0.0)
  ```
  > The endpoint accepts an OPTIONAL `?today=YYYY-MM-DD` query (test seam, defaults to UTC today) so the dense window is deterministic in tests. Document it as an internal/testing aid; the portal never sends it.
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_contract_series_router.py` → route missing.
- [ ] **Step 3 — Add the series endpoint.** In `apps/sidecar/src/gerti_sidecar/routers/contracts.py`:
  - Extend imports: `from typing import Literal`; `from gerti_sidecar.domain.contract_read_service import ContractReadService, consumed_percent_from, not_written_off_predicate` (merge with existing).
  - Add response models:
    ```python
    class SeriesPointOut(BaseModel):
        bucket: dt.date
        value: float


    class SeriesOut(BaseModel):
        granularity: str
        kind: str
        points: list[SeriesPointOut]
    ```
  - Add the endpoint:
    ```python
    @router.get("/{contract_id}/series", response_model=SeriesOut)
    async def get_series(
        contract_id: uuid.UUID = Path(...),
        granularity: Literal["day", "week"] = "day",
        today: dt.date | None = Query(None),
        _session_payload: SessionPayload = Depends(get_current_session),
        session: AsyncSession = Depends(get_tenant_session),
    ) -> SeriesOut:
        c = await session.get(Contract, contract_id)
        if c is None:  # RLS hid cross-tenant -> 404 (H2)
            raise HTTPException(status_code=404, detail="contract_not_found")
        s = await ContractReadService(session).series(c, granularity=granularity, today=today)
        return SeriesOut(
            granularity=s.granularity,
            kind=s.kind,
            points=[SeriesPointOut(bucket=p.bucket, value=p.value) for p in s.points],
        )
    ```
- [ ] **Step 4 — Run the full Sidecar gate.** Expected: **52 passed** (+1 test function). S1 + unknown-subdomain PASS.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/contracts.py apps/sidecar/tests/test_contract_series_router.py && git -c commit.gpgsign=false commit -m "feat(#1F-b): GET /v1/contracts/{id}/series densa diária/semanal (cap 400→week, exclui glosa approved, 404 cross-tenant)"
  ```

---

## Task 7 — `GET /v1/dashboard` — contract_count + balances_by_type + low_balance_alerts; read-only grep guard

**Goal:** §4.2.5. `routers/dashboard.py`. `contract_count`, `balances_by_type` (one per present type; `total_remaining` null for n/a), `low_balance_alerts` (warning <20%, critical ≤0%, saldo-bearing only). Reuses `ContractReadService.low_balance` + `ConsumptionService.balance`. Wire into `main.py`. Plus a static **read-only grep guard** asserting no mutation tokens in the new files (H3).

**Files:** Create `apps/sidecar/src/gerti_sidecar/routers/dashboard.py` · Modify `apps/sidecar/src/gerti_sidecar/main.py` · Create `apps/sidecar/tests/test_dashboard_router.py` · Create `apps/sidecar/tests/test_portal_read_only_guard.py`.

- [ ] **Step 1 — Failing tests.** Create `apps/sidecar/tests/test_dashboard_router.py`:
  ```python
  """GET /v1/dashboard: balances_by_type, low_balance thresholds, n/a never alerts, RLS-scoped."""

  from __future__ import annotations

  import datetime as dt

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app
  from gerti_sidecar.models import (
      ConsumptionEvent, Contract, Tenant, TenantBranding, ZnunyInstance,
  )
  from gerti_sidecar.models.enums import ContractType


  @pytest.mark.asyncio
  async def test_dashboard_balances_and_low_alerts(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
          webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
      session.add(inst)
      await session.flush()
      a = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
                 znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
      session.add(a)
      await session.flush()
      session.add(TenantBranding(tenant_id=a.id, display_name="A"))
      # hour_bank 10h, consume 9.5h -> remaining 0.5h = 5% -> warning
      hb = Contract(tenant_id=a.id, code="HB", type=ContractType.hour_bank,
                    starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                    initial_hours=10, unit_price_brl=100, created_by="seed")
      # credit_brl 1000, consume 1000 -> remaining 0 = critical
      cr = Contract(tenant_id=a.id, code="CR", type=ContractType.credit_brl,
                    starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                    initial_amount_brl=1000, unit_price_brl=100, created_by="seed")
      # closed_value -> NEVER alerts
      cv = Contract(tenant_id=a.id, code="CV", type=ContractType.closed_value,
                    starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                    initial_amount_brl=9000, unit_price_brl=9000, created_by="seed")
      session.add_all([hb, cr, cv])
      await session.flush()
      session.add(ConsumptionEvent(contract_id=hb.id,
          occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC), source_kind="ticket_work",
          source_ref="r", billable_minutes=570, recorded_by="seed"))  # 9.5h
      session.add(ConsumptionEvent(contract_id=cr.id,
          occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC), source_kind="ticket_work",
          source_ref="r", billable_minutes=0, billable_amount_brl=1000, recorded_by="seed"))
      await session.commit()
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      ha = {"host": "aurora.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          assert (await cl.get("/v1/dashboard", headers=ha)).status_code == 401
          cl.cookies.set("gsid", encode_session(str(a.id), "joe", st))
          r = await cl.get("/v1/dashboard", headers=ha)
          assert r.status_code == 200
          body = r.json()
          assert body["contract_count"] == 3
          types = {b["type"]: b for b in body["balances_by_type"]}
          assert types["closed_value"]["total_remaining"] is None
          assert types["hour_bank"]["total_remaining"] == pytest.approx(0.5)
          alerts = {al["code"]: al for al in body["low_balance_alerts"]}
          assert alerts["HB"]["severity"] == "warning"
          assert alerts["CR"]["severity"] == "critical"
          assert "CV" not in alerts  # closed_value never alerts
  ```
  Create `apps/sidecar/tests/test_portal_read_only_guard.py`:
  ```python
  """Static guard: the #1F-b read paths NEVER mutate the #1C domain (H3)."""

  from __future__ import annotations

  from pathlib import Path

  import pytest

  _SRC = Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
  _FILES = [
      _SRC / "domain" / "contract_read_service.py",
      _SRC / "routers" / "dashboard.py",
      _SRC / "routers" / "contracts.py",
  ]
  _FORBIDDEN = (
      ".add(", ".add_all(", ".flush(", ".commit(", ".delete(",
      "insert(", "update(", ".record(", ".close(", ".apply_adjustment(", ".renew(",
  )


  @pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
  def test_no_mutation_tokens(path):
      text = path.read_text()
      hits = [tok for tok in _FORBIDDEN if tok in text]
      assert hits == [], f"{path.name} contains mutation token(s): {hits}"
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/sidecar && uv run pytest -q tests/test_dashboard_router.py tests/test_portal_read_only_guard.py` → route missing / guard fails on missing file.
- [ ] **Step 3 — Implement the dashboard router.** Create `apps/sidecar/src/gerti_sidecar/routers/dashboard.py`:
  ```python
  """GET /v1/dashboard — resumo + alertas de saldo baixo, read-only, tenant da sessão (RLS)."""

  from __future__ import annotations

  from collections import defaultdict

  from fastapi import APIRouter, Depends
  from pydantic import BaseModel
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from gerti_sidecar.auth.session import SessionPayload, get_current_session
  from gerti_sidecar.db import get_tenant_session
  from gerti_sidecar.domain.consumption_service import ConsumptionService
  from gerti_sidecar.domain.contract_read_service import ContractReadService
  from gerti_sidecar.models import Contract

  router = APIRouter(prefix="/dashboard", tags=["portal"])


  class BalanceByType(BaseModel):
      type: str
      kind: str
      contract_count: int
      total_remaining: float | None


  class LowBalanceAlertOut(BaseModel):
      contract_id: str
      code: str
      type: str
      kind: str
      remaining: float
      consumed_percent: float | None
      severity: str


  class DashboardOut(BaseModel):
      contract_count: int
      balances_by_type: list[BalanceByType]
      low_balance_alerts: list[LowBalanceAlertOut]


  @router.get("", response_model=DashboardOut)
  async def get_dashboard(
      _session_payload: SessionPayload = Depends(get_current_session),
      session: AsyncSession = Depends(get_tenant_session),
  ) -> DashboardOut:
      contracts = (
          await session.execute(select(Contract).order_by(Contract.code))
      ).scalars().all()
      cons = ConsumptionService(session)
      reads = ContractReadService(session)

      counts: dict[str, int] = defaultdict(int)
      kinds: dict[str, str] = {}
      totals: dict[str, float | None] = {}
      alerts: list[LowBalanceAlertOut] = []
      for c in contracts:
          bal = await cons.balance(c.id)
          t = c.type.value
          counts[t] += 1
          kinds[t] = bal.kind
          if bal.remaining is None:
              totals.setdefault(t, None)  # n/a stays None
          else:
              prev = totals.get(t)
              totals[t] = (prev or 0.0) + float(bal.remaining) if prev is not None or t not in totals else float(bal.remaining)
          alert = await reads.low_balance(c)
          if alert is not None:
              alerts.append(
                  LowBalanceAlertOut(
                      contract_id=str(alert.contract_id),
                      code=alert.code,
                      type=alert.type,
                      kind=alert.kind,
                      remaining=alert.remaining,
                      consumed_percent=alert.consumed_percent,
                      severity=alert.severity,
                  )
              )
      balances = [
          BalanceByType(
              type=t, kind=kinds[t], contract_count=counts[t], total_remaining=totals.get(t)
          )
          for t in sorted(counts)
      ]
      return DashboardOut(
          contract_count=len(contracts),
          balances_by_type=balances,
          low_balance_alerts=alerts,
      )
  ```
  > **Total-remaining accumulation note:** for saldo-bearing types sum `float(remaining)`; for `n/a` keep `None`. The conditional above keeps `None` for n/a and sums the rest. The executing worker MUST verify the test asserts `hour_bank total_remaining == 0.5` and `closed_value total_remaining is None`; if the one-liner accumulation reads awkwardly to mypy/ruff, refactor to an explicit `if bal.remaining is None: totals[t] = None elif totals.get(t) is None: totals[t] = float(bal.remaining) else: totals[t] += float(bal.remaining)` (same behavior) — keep it readable and green.
- [ ] **Step 4 — Wire the router.** Modify `apps/sidecar/src/gerti_sidecar/main.py`: change the import to `from gerti_sidecar.routers import auth, branding, contracts, dashboard, health, me` and after `app.include_router(contracts.router, prefix=settings.api_v1_prefix)` add `app.include_router(dashboard.router, prefix=settings.api_v1_prefix)`.
- [ ] **Step 5 — Run the full Sidecar gate.** Expected: **55 passed** (52 + dashboard test [1] + read-only guard [3 parametrized = 3 functions] = +3 → wait: count test FUNCTIONS: dashboard 1 + guard parametrized counts as 3 collected = +4 → **56 passed**). State the OBSERVED count after running; expected **56 passed** (52 + 1 dashboard + 3 parametrized guard cases). S1 + unknown-subdomain PASS.
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/src/gerti_sidecar/routers/dashboard.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_dashboard_router.py apps/sidecar/tests/test_portal_read_only_guard.py && git -c commit.gpgsign=false commit -m "feat(#1F-b): GET /v1/dashboard (balances_by_type + low_balance warning<20%/critical≤0) + guard read-only estático"
  ```

---

## Task 8 — Pure-SVG chart components + vitest (ProgressBar, AreaChart, Sparkline)

**Goal:** §4.3.3. SSR-safe, brand-var-driven, pure `props → <svg>` (H6). Unit-tested by vitest with data props (incl. empty state + clamp 100%).

**Files:** Modify `apps/portal/nuxt.config.ts` (components scan, no path prefix) · Create `apps/portal/components/charts/ProgressBar.vue` · `AreaChart.vue` · `Sparkline.vue` · Create `apps/portal/test/charts.test.ts`.

> **VERIFIED convention:** this portal has NO `app/` dir; Nuxt 3 default scans `components/` at the project root. To keep bare-name auto-imports (`<ProgressBar>`, `<AreaChart>`, `<Sparkline>`, `<LowBalanceAlerts>`, `<WasSignature>`) regardless of subdirectory, add a `components` config with `pathPrefix: false`. All chart/util files live under `apps/portal/components/...` (NOT `app/components/`).

- [ ] **Step 0 — Components config.** Modify `apps/portal/nuxt.config.ts`: add (after the `modules: [...]` line) `components: [{ path: '~/components', pathPrefix: false }],` so directory-nested components auto-import by their bare filename.
- [ ] **Step 1 — Failing test.** Create `apps/portal/test/charts.test.ts`:
  ```ts
  import { mount } from '@vue/test-utils'
  import { describe, expect, it } from 'vitest'
  import AreaChart from '../components/charts/AreaChart.vue'
  import ProgressBar from '../components/charts/ProgressBar.vue'

  describe('ProgressBar', () => {
    it('clamps percent to 100 and uses brand var', () => {
      const w = mount(ProgressBar, { props: { percent: 250 } })
      const html = w.html()
      expect(html).toContain('var(--brand-primary)')
      // width never exceeds 100%
      expect(html).toMatch(/width:\s*100%/)
    })
    it('renders 0% for null percent without throwing', () => {
      const w = mount(ProgressBar, { props: { percent: null } })
      expect(w.html()).toMatch(/width:\s*0%/)
    })
  })

  describe('AreaChart', () => {
    it('renders an empty state when no points', () => {
      const w = mount(AreaChart, { props: { points: [] } })
      expect(w.text()).toContain('Sem dados')
    })
    it('emits an svg path from points and uses brand var', () => {
      const w = mount(AreaChart, {
        props: { points: [
          { bucket: '2026-01-01', value: 0 },
          { bucket: '2026-01-02', value: 2 },
          { bucket: '2026-01-03', value: 1 },
        ] },
      })
      const html = w.html()
      expect(html).toContain('<path')
      expect(html).toContain('var(--brand-primary)')
      // SSR-safe: fixed viewBox, no width/height pixel binding from window
      expect(html).toContain('viewBox')
    })
  })
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/portal && corepack pnpm exec vitest run test/charts.test.ts` → cannot find components.
- [ ] **Step 3 — ProgressBar.vue.** Create `apps/portal/components/charts/ProgressBar.vue`:
  ```vue
  <script setup lang="ts">
  const props = withDefaults(defineProps<{
    percent: number | null
    overage?: boolean
  }>(), { overage: false })

  const clamped = computed(() => {
    const p = props.percent
    if (p == null || Number.isNaN(p)) return 0
    return Math.max(0, Math.min(100, p))
  })
  </script>

  <template>
    <div class="h-2 w-full overflow-hidden rounded-full bg-neutral-100">
      <div
        class="h-full rounded-full transition-all"
        :class="overage ? 'opacity-90' : ''"
        :style="{ width: `${clamped}%`, background: 'var(--brand-primary)' }"
      />
    </div>
  </template>
  ```
- [ ] **Step 4 — AreaChart.vue.** Create `apps/portal/components/charts/AreaChart.vue`:
  ```vue
  <script setup lang="ts">
  interface Point { bucket: string, value: number }
  const props = withDefaults(defineProps<{
    points: Point[]
    height?: number
    width?: number
  }>(), { height: 120, width: 480 })

  // Deterministic gradient id (SSR-safe, stable across server+client — H6).
  const gid = useId()

  const path = computed(() => {
    const pts = props.points
    if (!pts.length) return { area: '', line: '' }
    const w = props.width
    const h = props.height
    const max = Math.max(1, ...pts.map(p => p.value))
    const stepX = pts.length > 1 ? w / (pts.length - 1) : 0
    const xy = pts.map((p, i) => {
      const x = i * stepX
      const y = h - (p.value / max) * h
      return [x, y] as const
    })
    const line = xy.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
    const area = `${line} L${w.toFixed(2)},${h} L0,${h} Z`
    return { area, line }
  })
  </script>

  <template>
    <div v-if="!points.length" class="flex h-[120px] items-center justify-center text-sm text-neutral-400">
      Sem dados de consumo no período
    </div>
    <svg
      v-else
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="none"
      class="h-32 w-full"
      role="img"
      aria-label="Consumo ao longo do tempo"
    >
      <defs>
        <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--brand-primary)" stop-opacity="0.35" />
          <stop offset="100%" stop-color="var(--brand-primary)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="path.area" :fill="`url(#${gid})`" />
      <path :d="path.line" fill="none" stroke="var(--brand-primary)" stroke-width="2" vector-effect="non-scaling-stroke" />
    </svg>
  </template>
  ```
- [ ] **Step 5 — Sparkline.vue.** Create `apps/portal/components/charts/Sparkline.vue`:
  ```vue
  <script setup lang="ts">
  interface Point { bucket: string, value: number }
  const props = withDefaults(defineProps<{ points: Point[] }>(), { points: () => [] })
  const line = computed(() => {
    const pts = props.points
    if (!pts.length) return ''
    const w = 120
    const h = 28
    const max = Math.max(1, ...pts.map(p => p.value))
    const stepX = pts.length > 1 ? w / (pts.length - 1) : 0
    return pts.map((p, i) => {
      const x = i * stepX
      const y = h - (p.value / max) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  })
  </script>

  <template>
    <svg v-if="points.length" viewBox="0 0 120 28" preserveAspectRatio="none" class="h-7 w-full" aria-hidden="true">
      <path :d="line" fill="none" stroke="var(--brand-primary)" stroke-width="1.5" vector-effect="non-scaling-stroke" />
    </svg>
    <div v-else class="h-7" />
  </template>
  ```
- [ ] **Step 6 — Run the Portal gate.** Expected: charts test green; lint/build green. (`corepack pnpm exec nuxt prepare` first so `useId`/auto-imports resolve in vitest.)
- [ ] **Step 7 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/nuxt.config.ts apps/portal/components/charts apps/portal/test/charts.test.ts && git -c commit.gpgsign=false commit -m "feat(#1F-b): componentes SVG puros (ProgressBar/AreaChart/Sparkline) SSR-safe brand-var + vitest"
  ```

---

## Task 9 — Portal server proxy routes for the new sidecar reads

**Goal:** §4.3.1. `server/api/portal/{dashboard,contracts/[id],contracts/[id]/consumption,contracts/[id]/series}.get.ts`, each via `sidecarFetch` (forwards cookie + `x-forwarded-host` — H7). 401 → handler propagates status so the page redirects to `/login`.

**Files:** Create `apps/portal/server/api/portal/dashboard.get.ts` · `apps/portal/server/api/portal/contracts/[id].get.ts` · `apps/portal/server/api/portal/contracts/[id]/consumption.get.ts` · `apps/portal/server/api/portal/contracts/[id]/series.get.ts`.

- [ ] **Step 1 — dashboard proxy.** Create `apps/portal/server/api/portal/dashboard.get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const { status, data } = await sidecarFetch(event, '/v1/dashboard')
    if (status !== 200) { setResponseStatus(event, status); return null }
    return data
  })
  ```
- [ ] **Step 2 — detail proxy.** Create `apps/portal/server/api/portal/contracts/[id].get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const id = getRouterParam(event, 'id')
    const { status, data } = await sidecarFetch(event, `/v1/contracts/${id}`)
    if (status !== 200) { setResponseStatus(event, status); return null }
    return data
  })
  ```
- [ ] **Step 3 — consumption proxy.** Create `apps/portal/server/api/portal/contracts/[id]/consumption.get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const id = getRouterParam(event, 'id')
    const q = getQuery(event)
    const page = Number(q.page ?? 1)
    const pageSize = Number(q.page_size ?? 50)
    const { status, data } = await sidecarFetch(
      event,
      `/v1/contracts/${id}/consumption?page=${page}&page_size=${pageSize}`,
    )
    if (status !== 200) { setResponseStatus(event, status); return null }
    return data
  })
  ```
- [ ] **Step 4 — series proxy.** Create `apps/portal/server/api/portal/contracts/[id]/series.get.ts`:
  ```ts
  export default defineEventHandler(async (event) => {
    const id = getRouterParam(event, 'id')
    const q = getQuery(event)
    const granularity = q.granularity === 'week' ? 'week' : 'day'
    const { status, data } = await sidecarFetch(
      event,
      `/v1/contracts/${id}/series?granularity=${granularity}`,
    )
    if (status !== 200) { setResponseStatus(event, status); return null }
    return data
  })
  ```
- [ ] **Step 5 — Run the Portal gate.** Expected: lint + build green (proxies are exercised end-to-end in Task 13).
- [ ] **Step 6 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/server/api/portal/dashboard.get.ts "apps/portal/server/api/portal/contracts/[id].get.ts" "apps/portal/server/api/portal/contracts/[id]/consumption.get.ts" "apps/portal/server/api/portal/contracts/[id]/series.get.ts" && git -c commit.gpgsign=false commit -m "feat(#1F-b): rotas server proxy do portal (dashboard + contract detail/consumption/series) encaminhando cookie+x-forwarded-host"
  ```

---

## Task 10 — Rich dashboard page `/` (cards + progress bars + low-balance alerts + sparklines)

**Goal:** §4.3.2 dashboard. Replace `pages/index.vue` to fetch `/api/portal/dashboard` + `/api/portal/contracts`, render contract cards with the SVG `ProgressBar` (using the REAL `consumed_percent` from the sidecar — no more heuristic), a `LowBalanceAlerts` band (amber/red, NEVER brand — H8), and optional per-card sparkline. Keep SSR auth guard + branding.

**Files:** Modify `apps/portal/pages/index.vue` · Create `apps/portal/components/LowBalanceAlerts.vue`.

- [ ] **Step 1 — LowBalanceAlerts.vue.** Create `apps/portal/components/LowBalanceAlerts.vue`:
  ```vue
  <script setup lang="ts">
  interface Alert {
    contract_id: string, code: string, type: string, kind: string
    remaining: number, consumed_percent: number | null, severity: 'warning' | 'critical'
  }
  defineProps<{ alerts: Alert[] }>()

  // Semantic colors — FIXED, never --brand-primary (an alert must read as an
  // alert in ANY tenant brand — Spec §4.3.2 / H8).
  const META: Record<string, { ring: string, text: string, icon: string, label: string }> = {
    warning: { ring: 'border-amber-300 bg-amber-50', text: 'text-amber-800', icon: 'i-lucide-alert-triangle', label: 'Saldo baixo' },
    critical: { ring: 'border-red-300 bg-red-50', text: 'text-red-800', icon: 'i-lucide-alert-octagon', label: 'Saldo esgotado' },
  }
  </script>

  <template>
    <div v-if="alerts.length" class="mb-6 space-y-2">
      <NuxtLink
        v-for="a in alerts"
        :key="a.contract_id"
        :to="`/contratos/${a.contract_id}`"
        class="flex items-center gap-3 rounded-xl border px-4 py-3 transition hover:shadow-sm"
        :class="META[a.severity].ring"
      >
        <UIcon :name="META[a.severity].icon" class="h-5 w-5" :class="META[a.severity].text" />
        <div class="min-w-0">
          <p class="text-sm font-semibold" :class="META[a.severity].text">
            {{ META[a.severity].label }} — {{ a.code }}
          </p>
          <p class="text-xs text-neutral-500">
            Restam {{ a.remaining.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) }}
            {{ a.kind === 'hours' ? 'h' : a.kind === 'brl' ? 'em crédito' : 'serviços' }}
          </p>
        </div>
        <UIcon name="i-lucide-chevron-right" class="ml-auto h-4 w-4 text-neutral-400" />
      </NuxtLink>
    </div>
  </template>
  ```
- [ ] **Step 2 — Rewrite `pages/index.vue`.** Replace the body so it: keeps the SSR auth guard (`/api/portal/me` → `navigateTo('/login')`); fetches `/api/portal/dashboard` (alerts) and `/api/portal/contracts` (cards); renders `<LowBalanceAlerts :alerts="dashboard?.low_balance_alerts ?? []" />` above the grid; per card links to `/contratos/${c.id}` and uses `<ProgressBar :percent="c.consumed_percent" />` (the REAL value — delete the `progress()` heuristic). Keep empty/loading states, branding header, `saldoBig`/`saldoLabel`/`fmtDate`/type+status maps. The new `ContractItem` interface gains `id: string` and `consumed_percent: number | null`. Full replacement:
  ```vue
  <script setup lang="ts">
  import type { Branding } from '#shared/branding'
  import { DEFAULT_BRANDING } from '#shared/branding'

  interface Saldo { kind: string, remaining: number | null }
  interface ContractItem {
    id: string, code: string, type: string, status: string
    starts_on: string, ends_on: string, saldo: Saldo, consumed_percent: number | null
  }
  interface Alert {
    contract_id: string, code: string, type: string, kind: string
    remaining: number, consumed_percent: number | null, severity: 'warning' | 'critical'
  }
  interface Dashboard {
    contract_count: number
    balances_by_type: { type: string, kind: string, contract_count: number, total_remaining: number | null }[]
    low_balance_alerts: Alert[]
  }

  const headers = useRequestHeaders(['cookie'])
  const { data: me } = await useAsyncData('me', () =>
    $fetch('/api/portal/me', { headers }).catch(() => null))
  if (!me.value) await navigateTo('/login')

  const { data: dashboard } = await useAsyncData('dashboard', () =>
    $fetch<Dashboard>('/api/portal/dashboard', { headers }).catch(() => null))
  const { data: contracts } = await useAsyncData('contracts', () =>
    $fetch<ContractItem[]>('/api/portal/contracts', { headers })
      .catch(() => [] as ContractItem[]))

  const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
  const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

  const TYPE_LABEL: Record<string, string> = {
    hour_bank: 'Banco de horas', credit_brl: 'Crédito (R$)', credit_shared: 'Crédito compartilhado',
    service_count: 'Pacote de serviços', closed_value: 'Valor fechado', saas_product: 'Assinatura',
  }
  const STATUS_META: Record<string, { label: string, color: 'success' | 'warning' | 'neutral' | 'error' }> = {
    active: { label: 'Ativo', color: 'success' }, suspended: { label: 'Suspenso', color: 'warning' },
    expired: { label: 'Expirado', color: 'error' }, terminated: { label: 'Encerrado', color: 'neutral' },
    draft: { label: 'Rascunho', color: 'neutral' },
  }
  const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
  const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
  function typeLabel(t: string) { return TYPE_LABEL[t] ?? t }
  function statusMeta(s: string) { return STATUS_META[s] ?? { label: s, color: 'neutral' as const } }
  function saldoBig(c: ContractItem): string {
    const r = c.saldo?.remaining; const kind = c.saldo?.kind
    if (r == null) return '—'
    if (kind === 'hours') return `${num.format(r)} h`
    if (kind === 'brl') return brl.format(r)
    if (kind === 'services') return `${num.format(r)} serviços`
    return num.format(r)
  }
  function saldoLabel(c: ContractItem): string {
    const kind = c.saldo?.kind
    if (kind === 'hours') return 'Saldo de horas'
    if (kind === 'brl') return 'Saldo disponível'
    if (kind === 'services') return 'Serviços restantes'
    return 'Saldo'
  }
  function fmtDate(iso: string): string {
    if (!iso) return ''
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
  }
  </script>

  <template>
    <div class="mx-auto max-w-6xl px-5 py-8">
      <header class="mb-8">
        <p class="text-sm text-neutral-500">{{ tenantName }}</p>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-neutral-900">Seus contratos</h1>
        <p class="mt-1 text-sm text-neutral-500">Acompanhe saldos, tipos e vigências dos seus contratos.</p>
      </header>

      <LowBalanceAlerts :alerts="dashboard?.low_balance_alerts ?? []" />

      <UCard v-if="!contracts || contracts.length === 0" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <span class="inline-flex h-12 w-12 items-center justify-center rounded-full text-white"
            :style="{ background: 'var(--brand-primary)' }">
            <UIcon name="i-lucide-file-text" class="h-6 w-6" />
          </span>
          <p class="font-display text-lg font-semibold text-neutral-800">Nenhum contrato ainda</p>
          <p class="max-w-sm text-sm text-neutral-500">Quando um contrato for ativado para você, ele aparecerá aqui.</p>
        </div>
      </UCard>

      <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <NuxtLink v-for="c in contracts" :key="c.id" :to="`/contratos/${c.id}`" class="block">
          <UCard class="h-full transition hover:shadow-md" :ui="{ body: 'space-y-4' }">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="font-display text-base font-bold tracking-tight text-neutral-900">{{ c.code }}</p>
                <UBadge color="primary" variant="subtle" size="sm" class="mt-1.5">{{ typeLabel(c.type) }}</UBadge>
              </div>
              <UBadge :color="statusMeta(c.status).color" variant="soft" size="sm">{{ statusMeta(c.status).label }}</UBadge>
            </div>
            <div>
              <p class="text-xs uppercase tracking-wide text-neutral-400">{{ saldoLabel(c) }}</p>
              <p class="font-display text-3xl font-extrabold tracking-tight text-neutral-900">{{ saldoBig(c) }}</p>
              <ProgressBar v-if="c.consumed_percent != null" class="mt-3" :percent="c.consumed_percent" />
            </div>
            <div class="flex items-center gap-1.5 text-xs text-neutral-500">
              <UIcon name="i-lucide-calendar" class="h-3.5 w-3.5" />
              <span>{{ fmtDate(c.starts_on) }} — {{ fmtDate(c.ends_on) }}</span>
            </div>
          </UCard>
        </NuxtLink>
      </div>
    </div>
  </template>
  ```
- [ ] **Step 2b — Update the auth-guard test if needed.** `test/auth-guard.test.ts` asserts a redirect on null `me`; it remains valid. No change unless it imports a removed symbol — verify it passes.
- [ ] **Step 3 — Run the Portal gate.** Expected: lint + test + build green.
- [ ] **Step 4 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/pages/index.vue apps/portal/components/LowBalanceAlerts.vue && git -c commit.gpgsign=false commit -m "feat(#1F-b): dashboard rica (cards + ProgressBar real + alertas saldo baixo semânticos)"
  ```

---

## Task 11 — Contract detail page `/contratos/[id]` (hero saldo + area chart + cycles timeline + ledger + adjustment/renewal + parties)

**Goal:** §4.3.2 detail. SSR fetch detail + series + 1st consumption page; header (badges branded), hero saldo + `ProgressBar` + overage label, `AreaChart` from series, cycles timeline (pills + `totals` on closed), paginated ledger table w/ glosa indicators (pending amber, approved red strike = não conta, rejected gray) + `counts_toward_balance=false` marker, adjustment/renewal card, billing parties. Loading/empty/error states.

**Files:** Create `apps/portal/pages/contratos/[id].vue` · Create `apps/portal/components/contract/glosa.ts` · Create `apps/portal/test/contract-detail.test.ts`.

- [ ] **Step 1 — Failing render test.** Create `apps/portal/test/contract-detail.test.ts` (pure render-logic units — the glosa indicator mapping). Since the page does SSR fetch, test the PURE helper by extracting it to an importable util. Create `apps/portal/components/contract/glosa.ts`:
  ```ts
  export type GlosaStatus = 'pending' | 'approved' | 'rejected'
  export interface GlosaMeta { label: string, classes: string, strike: boolean }
  // Fixed semantic colors — never brand (H8).
  export function glosaMeta(status: GlosaStatus | null): GlosaMeta | null {
    if (status === null) return null
    if (status === 'approved') return { label: 'Glosado (não conta)', classes: 'text-red-700', strike: true }
    if (status === 'pending') return { label: 'Glosa em análise', classes: 'text-amber-700', strike: false }
    return { label: 'Glosa rejeitada', classes: 'text-neutral-500', strike: false }
  }
  ```
  Test `apps/portal/test/contract-detail.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest'
  import { glosaMeta } from '../components/contract/glosa'

  describe('glosaMeta', () => {
    it('approved -> strike, red, never brand', () => {
      const m = glosaMeta('approved')!
      expect(m.strike).toBe(true)
      expect(m.classes).toContain('red')
      expect(m.classes).not.toContain('brand')
    })
    it('pending -> amber, not strike', () => {
      const m = glosaMeta('pending')!
      expect(m.strike).toBe(false)
      expect(m.classes).toContain('amber')
    })
    it('null -> null', () => {
      expect(glosaMeta(null)).toBeNull()
    })
  })
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/portal && corepack pnpm exec vitest run test/contract-detail.test.ts` → cannot find `glosa.ts`.
- [ ] **Step 3 — Create the page.** Create `apps/portal/pages/contratos/[id].vue` (full code):
  ```vue
  <script setup lang="ts">
  import type { Branding } from '#shared/branding'
  import { DEFAULT_BRANDING } from '#shared/branding'
  import { glosaMeta } from '~/components/contract/glosa'

  interface Saldo { kind: string, remaining: number | null }
  interface Cycle {
    id: string, kind: string, period_start: string, period_end: string
    status: string, closed_at: string | null, totals: Record<string, number> | null
  }
  interface Detail {
    id: string, code: string, type: string, status: string, starts_on: string, ends_on: string
    initial_hours: number | null, initial_amount_brl: number | null, initial_service_count: number | null
    unit_price_brl: number | null, saldo: Saldo, consumed_percent: number | null
    cycles: Cycle[]
    adjustment_rule: { index_code: string, cadence_months: number, next_run_on: string, cap_percent: number | null, last_applied_on: string | null, last_applied_percent: number | null } | null
    renewal_policy: { auto_renew: boolean, notice_days: number, next_review_on: string, renewal_term_months: number | null } | null
    billing_parties: { legal_name: string, document: string, fiscal_address: Record<string, unknown>, payment_method: string | null }[]
  }
  interface SeriesPoint { bucket: string, value: number }
  interface Series { granularity: string, kind: string, points: SeriesPoint[] }
  interface CItem {
    id: number, occurred_at: string, source_kind: string, source_ref: string
    billable_minutes: number, billable_amount_brl: number
    glosa: { status: 'pending' | 'approved' | 'rejected' } | null, counts_toward_balance: boolean
  }
  interface CPage { page: number, page_size: number, total: number, items: CItem[] }

  const route = useRoute()
  const id = computed(() => String(route.params.id))
  const headers = useRequestHeaders(['cookie'])

  const { data: me } = await useAsyncData('me-detail', () =>
    $fetch('/api/portal/me', { headers }).catch(() => null))
  if (!me.value) await navigateTo('/login')

  const { data: detail, error } = await useAsyncData(`detail-${id.value}`, () =>
    $fetch<Detail>(`/api/portal/contracts/${id.value}`, { headers }).catch(() => null))
  const { data: series } = await useAsyncData(`series-${id.value}`, () =>
    $fetch<Series>(`/api/portal/contracts/${id.value}/series`, { headers }).catch(() => null))

  const page = ref(1)
  const { data: ledger } = await useAsyncData(`ledger-${id.value}`, () =>
    $fetch<CPage>(`/api/portal/contracts/${id.value}/consumption?page=${page.value}&page_size=50`, { headers })
      .catch(() => null), { watch: [page] })

  const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)

  const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
  const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
  function fmtDate(iso: string | null): string {
    if (!iso) return '—'
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
  }
  function saldoBig(d: Detail): string {
    const r = d.saldo?.remaining; const k = d.saldo?.kind
    if (r == null) return '—'
    if (k === 'hours') return `${num.format(r)} h`
    if (k === 'brl') return brl.format(r)
    if (k === 'services') return `${num.format(r)} serviços`
    return num.format(r)
  }
  const overage = computed(() => {
    const d = detail.value
    return !!d && d.saldo?.remaining != null && d.saldo.remaining < 0
  })
  const CYCLE_STATUS: Record<string, { label: string, color: 'success' | 'warning' | 'neutral' }> = {
    open: { label: 'Aberto', color: 'warning' }, closed: { label: 'Fechado', color: 'success' },
    invoiced: { label: 'Faturado', color: 'neutral' },
  }
  function totalPages(p: CPage | null): number {
    if (!p) return 1
    return Math.max(1, Math.ceil(p.total / p.page_size))
  }
  </script>

  <template>
    <div class="mx-auto max-w-5xl px-5 py-8">
      <NuxtLink to="/" class="mb-6 inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800">
        <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar
      </NuxtLink>

      <div v-if="error || !detail" class="rounded-xl border border-neutral-200 p-8 text-center text-neutral-500">
        Não foi possível carregar este contrato.
      </div>

      <template v-else>
        <header class="mb-6 flex flex-wrap items-center gap-3">
          <h1 class="font-display text-2xl font-extrabold tracking-tight text-neutral-900">{{ detail.code }}</h1>
          <UBadge color="primary" variant="subtle">{{ detail.type }}</UBadge>
          <UBadge color="neutral" variant="soft">{{ detail.status }}</UBadge>
          <span class="ml-auto text-sm text-neutral-500">{{ fmtDate(detail.starts_on) }} — {{ fmtDate(detail.ends_on) }}</span>
        </header>

        <!-- Hero saldo -->
        <UCard class="mb-6">
          <p class="text-xs uppercase tracking-wide text-neutral-400">Saldo atual</p>
          <p class="font-display text-4xl font-extrabold tracking-tight text-neutral-900">{{ saldoBig(detail) }}</p>
          <ProgressBar v-if="detail.consumed_percent != null" class="mt-4" :percent="detail.consumed_percent" :overage="overage" />
          <p v-if="overage" class="mt-2 text-sm font-semibold text-red-700">Franquia excedida (overage)</p>
        </UCard>

        <!-- Série de consumo -->
        <UCard v-if="series && series.kind !== 'n/a'" class="mb-6">
          <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Consumo ao longo do tempo</p>
          <AreaChart :points="series.points" />
        </UCard>

        <!-- Timeline de ciclos -->
        <UCard v-if="detail.cycles.length" class="mb-6">
          <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Ciclos</p>
          <div class="space-y-2">
            <div v-for="cy in detail.cycles" :key="cy.id" class="flex flex-wrap items-center gap-3 rounded-lg border border-neutral-100 px-3 py-2">
              <UBadge :color="(CYCLE_STATUS[cy.status] ?? { color: 'neutral' }).color" variant="soft" size="sm">
                {{ (CYCLE_STATUS[cy.status] ?? { label: cy.status }).label }}
              </UBadge>
              <span class="text-sm text-neutral-600">{{ cy.kind }}</span>
              <span class="text-sm text-neutral-500">{{ fmtDate(cy.period_start) }} — {{ fmtDate(cy.period_end) }}</span>
              <span v-if="cy.totals" class="ml-auto text-xs text-neutral-500">
                Consumido {{ num.format((cy.totals.consumed_minutes ?? 0) / 60) }} h ·
                Overage {{ brl.format(cy.totals.overage_amount_brl ?? 0) }}
              </span>
            </div>
          </div>
        </UCard>

        <!-- Extrato paginado -->
        <UCard v-if="ledger" class="mb-6">
          <div class="mb-3 flex items-center justify-between">
            <p class="font-display text-sm font-semibold text-neutral-700">Extrato de consumo</p>
            <span class="text-xs text-neutral-400">{{ ledger.total }} lançamentos</span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="text-left text-xs uppercase tracking-wide text-neutral-400">
                <tr><th class="py-2">Data</th><th>Origem</th><th class="text-right">Min</th><th class="text-right">R$</th><th>Glosa</th></tr>
              </thead>
              <tbody>
                <tr v-for="it in ledger.items" :key="it.id" class="border-t border-neutral-100"
                  :class="!it.counts_toward_balance ? 'opacity-60' : ''">
                  <td class="py-2 text-neutral-600">{{ fmtDate(it.occurred_at) }}</td>
                  <td class="text-neutral-600">{{ it.source_kind }} · {{ it.source_ref }}</td>
                  <td class="text-right text-neutral-600" :class="it.glosa?.status === 'approved' ? 'line-through' : ''">{{ num.format(it.billable_minutes) }}</td>
                  <td class="text-right text-neutral-600" :class="it.glosa?.status === 'approved' ? 'line-through' : ''">{{ brl.format(it.billable_amount_brl) }}</td>
                  <td>
                    <span v-if="glosaMeta(it.glosa?.status ?? null)" class="text-xs font-medium" :class="glosaMeta(it.glosa?.status ?? null)!.classes">
                      {{ glosaMeta(it.glosa?.status ?? null)!.label }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="totalPages(ledger) > 1" class="mt-4 flex items-center justify-center gap-3">
            <UButton size="sm" variant="ghost" color="neutral" :disabled="page <= 1" icon="i-lucide-chevron-left" @click="page = Math.max(1, page - 1)" />
            <span class="text-sm text-neutral-500">{{ page }} / {{ totalPages(ledger) }}</span>
            <UButton size="sm" variant="ghost" color="neutral" :disabled="page >= totalPages(ledger)" icon="i-lucide-chevron-right" @click="page = page + 1" />
          </div>
        </UCard>

        <div class="grid gap-6 md:grid-cols-2">
          <!-- Reajuste & renovação -->
          <UCard v-if="detail.adjustment_rule || detail.renewal_policy">
            <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Reajuste & renovação</p>
            <dl class="space-y-1.5 text-sm">
              <template v-if="detail.adjustment_rule">
                <div class="flex justify-between"><dt class="text-neutral-500">Índice</dt><dd>{{ detail.adjustment_rule.index_code }}</dd></div>
                <div class="flex justify-between"><dt class="text-neutral-500">Cadência</dt><dd>{{ detail.adjustment_rule.cadence_months }} meses</dd></div>
                <div class="flex justify-between"><dt class="text-neutral-500">Teto</dt><dd>{{ detail.adjustment_rule.cap_percent != null ? `${detail.adjustment_rule.cap_percent}%` : '—' }}</dd></div>
                <div class="flex justify-between"><dt class="text-neutral-500">Próximo reajuste</dt><dd>{{ fmtDate(detail.adjustment_rule.next_run_on) }}</dd></div>
              </template>
              <template v-if="detail.renewal_policy">
                <div class="flex justify-between"><dt class="text-neutral-500">Auto-renovação</dt><dd>{{ detail.renewal_policy.auto_renew ? 'Sim' : 'Não' }}</dd></div>
                <div class="flex justify-between"><dt class="text-neutral-500">Aviso prévio</dt><dd>{{ detail.renewal_policy.notice_days }} dias</dd></div>
                <div class="flex justify-between"><dt class="text-neutral-500">Próxima revisão</dt><dd>{{ fmtDate(detail.renewal_policy.next_review_on) }}</dd></div>
              </template>
            </dl>
          </UCard>

          <!-- Partes de faturamento -->
          <UCard v-if="detail.billing_parties.length">
            <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Partes de faturamento</p>
            <div v-for="p in detail.billing_parties" :key="p.document" class="space-y-0.5 text-sm">
              <p class="font-medium text-neutral-800">{{ p.legal_name }}</p>
              <p class="text-neutral-500">{{ p.document }}</p>
              <p v-if="p.payment_method" class="text-neutral-500">Pagamento: {{ p.payment_method }}</p>
            </div>
          </UCard>
        </div>
      </template>
    </div>
  </template>
  ```
- [ ] **Step 4 — Run the Portal gate.** Expected: lint + test (glosa.ts unit) + build green.
- [ ] **Step 5 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add "apps/portal/pages/contratos/[id].vue" apps/portal/components/contract/glosa.ts apps/portal/test/contract-detail.test.ts && git -c commit.gpgsign=false commit -m "feat(#1F-b): página /contratos/[id] (hero saldo + AreaChart + ciclos + extrato glosa + reajuste/renovação/partes)"
  ```

---

## Task 12 — WAS signature footer (login + app shell) + vitest

**Goal:** §4.3.5. "Desenvolvido por WAS Soluções em Tecnologia", `text-xs`, muted, NEVER brand color, on the login screen footer AND the authenticated app shell footer. A vitest asserts the footer carries no brand class/style.

**Files:** Create `apps/portal/components/WasSignature.vue` · Modify `apps/portal/layouts/default.vue` · Modify `apps/portal/pages/login.vue` · Create `apps/portal/test/was-signature.test.ts`.

- [ ] **Step 1 — Failing test.** Create `apps/portal/test/was-signature.test.ts`:
  ```ts
  import { mount } from '@vue/test-utils'
  import { describe, expect, it } from 'vitest'
  import WasSignature from '../components/WasSignature.vue'

  describe('WasSignature', () => {
    it('shows the WAS credit, muted, never brand', () => {
      const w = mount(WasSignature)
      const html = w.html()
      expect(w.text()).toContain('WAS Soluções em Tecnologia')
      expect(html).toContain('text-xs')
      expect(html).not.toContain('--brand-primary')
      expect(html).not.toContain('--brand-accent')
    })
  })
  ```
- [ ] **Step 2 — Run, expect fail.** `cd /home/will/projetos/ground-control/apps/portal && corepack pnpm exec vitest run test/was-signature.test.ts` → component missing.
- [ ] **Step 3 — WasSignature.vue.** Create `apps/portal/components/WasSignature.vue`:
  ```vue
  <script setup lang="ts">
  // Crédito discreto de plataforma — muted, text-xs, NUNCA cor de marca (H8/§4.3.5).
  </script>

  <template>
    <p class="text-center text-xs text-neutral-400">
      Desenvolvido por
      <a href="https://was.dev.br" target="_blank" rel="noopener"
        class="font-medium underline-offset-2 hover:underline">WAS Soluções em Tecnologia</a>
    </p>
  </template>
  ```
- [ ] **Step 4 — App shell footer.** Modify `apps/portal/layouts/default.vue`: REPLACE the existing conditional `<footer ...>{{ b.display_name }} · {{ b.support_email }}</footer>` block with a footer that always carries the WAS signature on authed views (keep the optional brand support line above it, muted):
  ```vue
      <footer
        v-if="isAuthedView"
        class="border-t border-neutral-200/70 px-5 py-4 text-center"
      >
        <p v-if="b?.support_email" class="mb-1 text-xs text-neutral-400">
          {{ b.display_name }} · {{ b.support_email }}
        </p>
        <WasSignature />
      </footer>
  ```
- [ ] **Step 5 — Login footer.** Modify `apps/portal/pages/login.vue`: inside the form panel `<section ...>`, after the closing `</div>` of `class="w-full max-w-sm"` content but before the section closes, add a footer. Concretely, add right after the `</UForm>` closing tag (still inside `.max-w-sm`):
  ```vue
          <div class="mt-10">
            <WasSignature />
          </div>
  ```
- [ ] **Step 6 — Run the Portal gate.** Expected: was-signature test + all prior tests + lint + build green.
- [ ] **Step 7 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/portal/components/WasSignature.vue apps/portal/layouts/default.vue apps/portal/pages/login.vue apps/portal/test/was-signature.test.ts && git -c commit.gpgsign=false commit -m "feat(#1F-b): assinatura WAS discreta (login + app shell), text-xs muted nunca brand"
  ```

---

## Task 13 — Sidecar e2e smoke over the Aurora + TechNova seeds (rich endpoints, cross-tenant)

**Goal:** §8.3. Reuse `seed_demo_contracts.seed` + `seed_demo_branding.seed`. Assert: extended list has `id`+`consumed_percent`; detail of `AUR-HORAS-2026` returns cycles+saldo (pending glosa STILL counts → known remaining); consumption ledger shows the pending glosa with `counts_toward_balance=True`; series is dense; dashboard balances_by_type covers Aurora's 6 types; a TechNova session asking an Aurora contract id → 404.

**Files:** Create `apps/sidecar/tests/test_portal_rich_e2e.py`.

- [ ] **Step 1 — Failing test.** Create `apps/sidecar/tests/test_portal_rich_e2e.py`:
  ```python
  """E2E (#1F-b): rich read endpoints over the Aurora+TechNova seeds, cross-tenant 404.

  Aurora AUR-HORAS-2026 seed: events [90,120,150] min, pending glosa on event #0.
  Pending glosa STILL counts -> consumed = (90+120+150)/60 = 6.0h; initial 40h ->
  remaining 34.0h. counts_toward_balance is True for the pending-glosa event.
  """

  from __future__ import annotations

  import sys
  from pathlib import Path

  import pytest
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

  from gerti_sidecar import db
  from gerti_sidecar.auth.session import encode_session
  from gerti_sidecar.config import get_settings
  from gerti_sidecar.main import create_app

  _SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
  if str(_SCRIPTS) not in sys.path:
      sys.path.insert(0, str(_SCRIPTS))

  import seed_demo_branding  # noqa: E402
  import seed_demo_contracts  # noqa: E402


  @pytest.mark.asyncio
  async def test_rich_endpoints_two_tenants(engine, app_session_factory, session, monkeypatch):
      monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
      monkeypatch.setenv("ENVIRONMENT", "test")
      get_settings.cache_clear()
      await seed_demo_contracts.seed(session)
      await session.commit()
      aurora_id, technova_id = await seed_demo_branding.seed(session)
      await session.commit()
      monkeypatch.setattr(db, "AdminSessionLocal",
          async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
      monkeypatch.setattr(db, "SessionLocal", app_session_factory)
      app = create_app()
      st = get_settings()
      ha = {"host": "aurora.suporte.gerti.com.br"}
      ht = {"host": "technova.suporte.gerti.com.br"}
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://t") as cl:
          cl.cookies.set("gsid", encode_session(str(aurora_id), "eduardo.salvi", st))
          lst = (await cl.get("/v1/contracts", headers=ha)).json()
          assert len(lst) == 6
          assert all("id" in c and "consumed_percent" in c for c in lst)
          horas = next(c for c in lst if c["code"] == "AUR-HORAS-2026")
          assert horas["saldo"]["kind"] == "hours"
          assert horas["saldo"]["remaining"] == pytest.approx(34.0)  # pending glosa counts
          cid = horas["id"]

          det = (await cl.get(f"/v1/contracts/{cid}", headers=ha)).json()
          assert det["initial_hours"] == 40.0
          assert len(det["cycles"]) >= 1

          cons = (await cl.get(f"/v1/contracts/{cid}/consumption", headers=ha)).json()
          assert cons["total"] == 3
          # the pending-glosa event STILL counts
          pend = [it for it in cons["items"] if it["glosa"] and it["glosa"]["status"] == "pending"]
          assert pend and pend[0]["counts_toward_balance"] is True

          ser = (await cl.get(f"/v1/contracts/{cid}/series?today=2026-12-31", headers=ha)).json()
          assert ser["kind"] == "hours" and len(ser["points"]) >= 1

          dash = (await cl.get("/v1/dashboard", headers=ha)).json()
          assert dash["contract_count"] == 6
          types = {b["type"] for b in dash["balances_by_type"]}
          assert {"hour_bank", "credit_brl", "credit_shared", "service_count",
                  "closed_value", "saas_product"} <= types

          # cross-tenant: TechNova session asking Aurora's contract -> 404
          cl.cookies.clear()
          cl.cookies.set("gsid", encode_session(str(technova_id), "admin.tech@technova.example", st))
          assert (await cl.get(f"/v1/contracts/{cid}", headers=ht)).status_code == 404
  ```
  > **Executing worker — verify before relying on numbers:** confirm `seed_demo_contracts._CONTRACTS` has 6 entries and `AUR-HORAS-2026` events are `[90,120,150]` with the glosa PENDING on event #0 (it is, per audit). If a real value differs, set the assertion to the real value (do NOT hand-wave). `34.0h` follows from 40 − (90+120+150)/60 = 40 − 6.0 because the seed's only glosa is PENDING (counts).
- [ ] **Step 2 — Run, expect fail then green.** Run the test red (route shapes), then it passes once Tasks 2/4/5/6/7 are merged.
- [ ] **Step 3 — Run the full Sidecar gate.** Expected: **57 passed** (56 + 1 e2e function). S1 + unknown-subdomain PASS.
- [ ] **Step 4 — Commit.**
  ```
  cd /home/will/projetos/ground-control && git add apps/sidecar/tests/test_portal_rich_e2e.py && git -c commit.gpgsign=false commit -m "test(#1F-b): e2e dos endpoints ricos sobre seeds Aurora+TechNova (glosa pending conta, 404 cross-tenant)"
  ```

---

## Task 14 — Deploy (additive): rebuild --no-cache portal + recreate sidecar via `ssh gc`, public verify

**Goal:** §10. No migration. Rebuild the portal image `--no-cache` (new pages/components) and recreate the sidecar (new routers) on the VPS; verify both tenants over the Cloudflare edge. Branding/ingress already wired in #1F-a — this is a code-only redeploy.

**Files:** none (deploy operation).

- [ ] **Step 1 — Pull + rebuild + recreate on the VPS.**
  ```
  ssh gc 'cd ~/ground-control && git pull'
  ssh gc 'cd ~/ground-control && DC="docker compose --env-file .env --env-file .env.prod --profile gerti"; $DC build --no-cache portal && $DC up -d --force-recreate portal sidecar && $DC ps'
  ```
- [ ] **Step 2 — Public verification over the Cloudflare edge (1-level hosts).**
  ```
  ssh gc 'curl -fsS https://aurora.was.dev.br/ | grep -qi "Aurora" && echo AURORA_OK'
  ssh gc 'curl -fsS https://technova.was.dev.br/ | grep -qi "TechNova" && echo TECHNOVA_OK'
  ssh gc 'curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK'
  ssh gc 'curl -fsS https://api-dev.was.dev.br/v1/health && echo API_OK'
  ```
  All four must succeed (the new slice is additive; znuny-dev/api-dev untouched).
- [ ] **Step 3 — Spot-check a rich endpoint end-to-end (authenticated, optional but recommended).** Confirm `https://aurora.was.dev.br/contratos/<id>` renders (the MVP-BONITO task captures the screenshots). No commit (deploy step).

---

## Task 15 — `.ia/` docs + ADR D17 verification + MVP-BONITO screenshot gate

**Goal:** §8.4/§10. Update `.ia/ARCHITECTURE.md` + `.ia/INTEGRATION.md` (+ confirm ADR **D17** from Task 1); then the controller captures screenshots of Aurora (cyan) + TechNova (violet) — login, dashboard w/ charts+alerts, contract detail — and approves "real premium SaaS"; iterate if any element is raw/unstyled.

**Files:** Modify `.ia/ARCHITECTURE.md` · `.ia/INTEGRATION.md` · (`.ia/DECISIONS.md` already has D17 from Task 1).

- [ ] **Step 1 — ARCHITECTURE.md.** Add a "Portal #1F-b — visão de contratos rica (read-only)" subsection under the existing Portal section: the new read-only endpoints (`/v1/contracts` extended, `/v1/contracts/{id}`, `/v1/contracts/{id}/consumption`, `/v1/contracts/{id}/series`, `/v1/dashboard`), the `contract_read_service.py` centralizing the S3 glosa rule (ADR D17), pure-SVG chart components, the rich dashboard + `/contratos/[id]`, the discreet WAS signature; topology unchanged (`Browser → cloudflared → portal:3000 → sidecar:8001 → gerti schema RLS`); read-only over #1C (no mutation).
- [ ] **Step 2 — INTEGRATION.md.** Add "Construído vs pendente" rows: `/v1/contracts` (+id,+consumed_percent), `/v1/contracts/{id}`, `/v1/contracts/{id}/consumption`, `/v1/contracts/{id}/series`, `/v1/dashboard` (built, read-only); `contract_read_service` (built, S3 rule centralized); portal rich dashboard + detail + SVG charts + WAS footer (built). Note still-deferred (§9): tickets/catálogo/abrir-chamado (#1E), admin/onboarding/branding UI (#1G), OIDC (#1D), export/filters/i18n.
- [ ] **Step 3 — Verify ADR D17.** Confirm `.ia/DECISIONS.md` has D17 (authored in Task 1). Do NOT re-author; only verify it is present and consistent.
- [ ] **Step 4 — Commit docs.**
  ```
  cd /home/will/projetos/ground-control && git add .ia/ARCHITECTURE.md .ia/INTEGRATION.md && git -c commit.gpgsign=false commit -m "docs(#1F-b): ARCHITECTURE/INTEGRATION (endpoints ricos read-only + read-service + charts SVG + assinatura WAS)"
  ```
- [ ] **Step 5 — MVP-BONITO screenshot gate (controller).** Capture, via the Playwright MCP against the live edge (or local SSR with seeded branding), screenshots of: Aurora login, Aurora dashboard (cards + ProgressBar + low-balance alerts + sparkline), Aurora `/contratos/[id]` (hero saldo + AreaChart + cycles + ledger w/ glosa indicators + reajuste/renovação/partes); and the SAME three for TechNova (violet/dark). Bar: "real premium SaaS" — coherent hierarchy/spacing, correct fonts, brand-colored bars/charts, semantic (non-brand) alerts, polished loading/empty/error, responsive, discreet WAS signature present in BOTH tenants. If any element is raw/unstyled, iterate (adjust the relevant Vue) and re-shoot before declaring done. No commit unless a fix is applied (then commit the specific Vue file).

---

## Self-Review

### Spec-coverage table (each spec § → task)

| Spec § | Covered by |
|---|---|
| §1 Objetivo (visão rica read-only) | Tasks 1–15 |
| §2.1 Read-only absoluto sobre #1C | Tasks 1 (read service, no writes), 7 (grep guard H3), all router tasks |
| §2.2 Regras = código, não intuição | Task 1 (reuse `balance`/`totals`; S3 centralized — ADR D17) |
| §2.3 Mesma muralha auth/RLS | Tasks 4,5,6,7 (`get_current_session`+`get_tenant_session`; 404 cross-tenant) |
| §2.4 Gráficos SVG puro, sem lib | Tasks 8, 10, 11 |
| §2.5 MVP bonito verificável | Task 15 (screenshot gate) |
| §2.6 Assinatura WAS discreta | Task 12 |
| §2.7 Stack inalterada | All (no new dep; no migration) |
| §4.1 Regras #1C (A/B/C + reajuste/renovação) | Task 1 (balance/`not_written_off`), Task 4 (totals raw + adjustment/renewal read) |
| §4.2.1 `/v1/contracts` (+id,+consumed_percent) | Task 2 |
| §4.2.2 `/v1/contracts/{id}` detalhe | Task 4 |
| §4.2.3 `/v1/contracts/{id}/consumption` | Task 5 |
| §4.2.4 `/v1/contracts/{id}/series` | Tasks 1 (`series`), 6 (endpoint) |
| §4.2.5 `/v1/dashboard` | Tasks 1 (`low_balance`), 7 (endpoint) |
| §4.3.1 rotas server proxy | Task 9 |
| §4.3.2 páginas / e /contratos/[id] | Tasks 10, 11 |
| §4.3.3 componentes SVG | Task 8 |
| §4.3.4 estados/micro-interações | Tasks 10, 11 (loading/empty/error, hover) |
| §4.3.5 assinatura WAS | Task 12 |
| §5 Fluxos | Tasks 9–11, 13 |
| §6 Erros & segurança (404/401/403, RLS fail-closed, validação, read-only) | Tasks 4,5,6 (404 H2; 401/403 via get_current_session), 5,6 (clamp/granularity H4), 7 (read-only guard H3) |
| §7 R1 série longa (cap 400→week) | Tasks 1, 6 (H5) |
| §7 R2 N+1 dashboard (aceito, YAGNI) | Task 7 (reuse balance per-contract; no premature optimization) |
| §7 R3 consistência Aurora/TechNova | Task 15 (dual screenshot) |
| §8.1 testes sidecar | Tasks 1,2,4,5,6,7,13 |
| §8.2 testes portal (vitest) | Tasks 8 (charts), 11 (glosa util), 12 (WAS) |
| §8.3 e2e | Task 13 |
| §8.4 verificação visual | Task 15 |
| §9 YAGNI (exclusões) | **ABSENT by construction — see below** |
| §10 definição de pronto | Tasks 13, 14 (deploy aditivo), 15 (.ia + screenshots) |

### YAGNI exclusion confirmation

No task, file, or step creates or mentions as work: any write/mutation of contract/cycle/glosa/consumption/adjustment/renewal (read-only enforced by the Task 7 grep guard + `contract_read_service` doing only `select`/`get`/`balance`); tickets/service catalog/abrir-chamado (#1E); admin/onboarding/branding UI (#1G); OIDC/PKCE (#1D); multi-Znuny; export CSV/PDF; advanced filters/search; i18n; external chart libs (charts are hand-rolled SVG); dashboard N+1 optimization (R2 explicitly deferred). **Confirmed absent.**

### Placeholder scan

Targets `TODO`, `FIXME`, `similar to Task`, `handle edge cases`, `<placeholder>`, bare `...`: none. Every code step is complete and runnable. The only conditionals are explicit *verification* instructions (Task 8 component-dir check; Task 7 dashboard accumulation readability note; Task 13 seed-count confirmation) — these are worker verification aids, not unfinished code. The `...` inside `not_written_off_predicate()` docstrings does not appear; all bodies are concrete.

### Type / name consistency check

- `not_written_off_predicate()` / `ContractReadService` / `consumed_percent_from` / `series` / `low_balance` — defined Task 1, consumed Tasks 2 (`consumed_percent_from`), 4 (`consumed_percent_from`), 5 (`not_written_off_predicate` import + Python mirror), 6 (`ContractReadService.series`), 7 (`ContractReadService.low_balance`). Spelled identically.
- `Balance.kind`/`Balance.remaining` (#1C) — read-only everywhere; `kind ∈ {"hours","brl","services","n/a"}` matches `consumed_percent`/`low_balance`/series branching.
- `totals` JSONB keys read as-is (Task 4 `CycleItem.totals: dict[str,object]|None`); never recomputed.
- 404 cross-tenant — Tasks 4,5,6 each `session.get(Contract,id) is None → HTTPException(404)`; e2e Task 13 asserts TechNova→Aurora id = 404.
- Pagination — `page Query(ge=1)`, `page_size Query(ge=1,le=200)` default 50, clamp in body (Task 5); asserted (page_size=500→200) in Task 5.
- `granularity: Literal["day","week"]` (Task 6); cap 400→week in `ContractReadService.series` (Task 1), asserted Task 6 dense daily.
- Portal types: `ContractItem` gains `id:string`,`consumed_percent:number|null` (Tasks 2 backend ↔ 10 frontend); `Detail`/`Series`/`CPage` shapes mirror the Pydantic models field-for-field (Task 11 ↔ Tasks 4/5/6).
- SVG components `ProgressBar`/`AreaChart`/`Sparkline` (Task 8), `LowBalanceAlerts` (Task 10), `WasSignature` (Task 12), `glosaMeta` util (Task 11) — names stable; brand vars only in chart fills, semantic colors in alerts/glosa/WAS (H8).
- monkeypatch.setattr(db,...) in every new sidecar HTTP test (Tasks 4,5,6,7,13) — never bare `db.X =`.
- Test counts monotonic from verified baseline **46**: Task 1 +2 (48), Task 2 +0 (48, extended in place), Task 4 +1 (49), Task 5 +2 (51), Task 6 +1 (52), Task 7 +4 (56 — 1 dashboard + 3 parametrized guard cases), Task 13 +1 (57). Sequence: 46→48→48→49→51→52→56→57. **Final sidecar gate = 57 passed.** (Tasks 8/9/10/11/12 portal-only; Tasks 3/14/15 no sidecar test.)
- ADR: **D17** authored Task 1 (read-service / S3 centralized), verified Task 15. The exemplar's D14/D15/D16 are #1F-a's and untouched.

All gaps found during self-review were fixed inline before saving: (1) the dashboard `total_remaining` accumulation one-liner was flagged as awkward and a readable explicit-branch fallback was specified in Task 7 Step 3 to keep mypy/ruff green; (2) the SVG gradient id is `useId()` (deterministic, SSR-safe) instead of `Math.random` to avoid hydration mismatch (H6); (3) the series endpoint exposes an optional `?today=` test seam so dense-window assertions are deterministic without freezing the clock; (4) the consumption `counts_toward_balance` is computed in Python on the joined `Glosa.status` while series aggregates in SQL via `not_written_off_predicate()` — both reduce to "null OR != approved", asserted equivalent in Tasks 5 & 13, so the rule is not duplicated divergently; (5) the read-only grep guard (Task 7) statically forbids mutation tokens in the three new/edited backend files (H3), making "read-only" machine-checked rather than asserted on faith; (6) component directory placement was VERIFIED against the live repo (no `app/` dir → Nuxt scans root `components/`); the plan was corrected to place all chart/util components under `apps/portal/components/...` and adds a `components: [{ path: '~/components', pathPrefix: false }]` nuxt.config entry (Task 8 Step 0) so they auto-import by bare name (`<ProgressBar>` etc.) as the page/dashboard/layout templates reference them. All paths, test imports, and `git add` commands were made consistent with `components/` (no `app/components/` paths remain in any task).
