"""Gate local (testcontainers) do seeder demo + e2e de prod.

Prova, sem prod, os mesmos invariantes que os scripts checam em produção:
- seeder roda idempotente sob o role admin (BYPASSRLS);
- re-execução do seeder não duplica nem viola o trigger append-only;
- e2e sob o role gerti_sidecar (sujeito a RLS): 6 contratos visíveis no
  escopo do tenant, saldo 34.0h, ciclo fev fecha com 120min, reajuste
  clampado ao cap (216.00) e fail-closed 0/0.

Reusa as fixtures do conftest (`session` = admin; `app_session_factory` =
gerti_sidecar). Os scripts são importados de ../scripts (fora de `src`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.models import Contract, Tenant

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import e2e_prod_check  # noqa: E402
import seed_demo_contracts  # noqa: E402


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_e2e_passes(session, app_session_factory):
    # --- seed as admin (BYPASSRLS) ---
    tenant_id = await seed_demo_contracts.seed(session)
    await session.commit()

    # idempotency: a second run must not raise nor duplicate, and must not
    # trip the append-only trigger (consumption guarded by webhook_event_id).
    tenant_id_2 = await seed_demo_contracts.seed(session)
    await session.commit()
    assert tenant_id_2 == tenant_id

    n_contracts = await session.scalar(
        select(func.count()).select_from(Contract).where(Contract.tenant_id == tenant_id)
    )
    assert n_contracts == 6
    n_tenants = await session.scalar(
        select(func.count()).select_from(Tenant).where(Tenant.id == tenant_id)
    )
    assert n_tenants == 1

    # invariants from the SEEDED state, asserted directly under tenant scope
    # BEFORE the e2e mutates anything (e2e records a Feb event + adjusts price).
    async with db.tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        codes = set((await s.execute(select(Contract.code))).scalars().all())
        assert e2e_prod_check.EXPECTED_CODES.issubset(codes)
        horas = (
            await s.execute(select(Contract).where(Contract.code == "AUR-HORAS-2026"))
        ).scalar_one()
        bal = await ConsumptionService(s).balance(horas.id)
        # 40 - (90+120+150)/60 = 34.0 (pending glosa does NOT reduce balance)
        assert bal.kind == "hours"
        assert bal.remaining is not None and abs(bal.remaining - 34.0) < 1e-9

    # --- e2e as gerti_sidecar (RLS-subject): cycle close + capped adjustment ---
    failures = await e2e_prod_check.run_e2e(app_session_factory, tenant_id)
    assert failures == 0

    # after e2e applied the capped adjustment once: 200 * 1.08 = 216.00
    async with db.tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        credito = (
            await s.execute(select(Contract).where(Contract.code == "AUR-CREDITO-2026"))
        ).scalar_one()
        assert float(credito.unit_price_brl or 0) == 216.00

    # fail-closed under the unprivileged role with no GUC
    async with app_session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(Tenant)) == 0
        assert await s.scalar(select(func.count()).select_from(Contract)) == 0
