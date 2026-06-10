"""Console /v1/admin/tenants/{id}/invoices — gera do ciclo, marca paga, cancela, lista.

Todos sob get_admin_session (gsid_adm). Espelha test_admin_timer_router.py.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.main import create_app
from gerti_sidecar.models import ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind


async def _seed_tenant_with_closed_cycle(session, app_session_factory, subdomain):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name=subdomain,
        trade_name=subdomain,
        document=subdomain,
        znuny_customer_id=subdomain.upper(),
        znuny_instance_id=inst.id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.commit()
    async with db.tenant_session_scope(t.id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="AUR-1",
                type=ContractType.credit_brl,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_amount_brl=20000,
                created_by="seed",
            )
        )
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
        )
        s.add(cyc)
        await s.flush()
        await CycleService(s).close(cyc.id)
        cyc_id = cyc.id
    return t, cyc_id


@pytest.mark.asyncio
async def test_admin_invoice_lifecycle(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t, cyc_id = await _seed_tenant_with_closed_cycle(session, app_session_factory, "aurora")

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        base = f"/v1/admin/tenants/{t.id}/invoices"
        # sem gsid_adm → 401
        assert (await c.post(base, json={"cycle_id": str(cyc_id)})).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        # tenant inválido → 404
        bad = await c.post("/v1/admin/tenants/not-a-uuid/invoices", json={"cycle_id": str(cyc_id)})
        assert bad.status_code == 404

        # cria fatura a partir do ciclo → 201
        r = await c.post(base, json={"cycle_id": str(cyc_id)})
        assert r.status_code == 201, r.text
        number = r.json()["number"]
        assert number == 1
        assert r.json()["status"] == "open"

        # idempotência: mesmo ciclo → 409
        again = await c.post(base, json={"cycle_id": str(cyc_id)})
        assert again.status_code == 409

        # lista
        lst = await c.get(base)
        assert lst.status_code == 200
        assert len(lst.json()) == 1

        # marca paga
        paid = await c.post(f"{base}/{number}/paid")
        assert paid.status_code == 200
        assert paid.json()["status"] == "paid"

        # paid é terminal → void falha 409
        v = await c.post(f"{base}/{number}/void")
        assert v.status_code == 409
