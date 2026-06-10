"""Portal /v1/invoices — admin lista/baixa PDF; helpdesk 403; pdf on-demand.

Espelha test_contracts_router.py (cookie gsid + host do subdomínio).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.main import create_app
from gerti_sidecar.models import ContractCycle, Invoice, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind


async def _seed(session, app_session_factory):
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
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(t)
    await session.flush()
    session.add(
        TenantBranding(tenant_id=t.id, display_name="Aurora Móveis", primary_color="#e67e22")
    )
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
        await ConsumptionService(s).record(
            RecordConsumption(
                contract_id=c.id,
                occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="t:1",
                billable_minutes=60,
                billable_amount_brl=200,
                recorded_by="t",
                webhook_event_id=uuid.uuid4(),
            )
        )
        await CycleService(s).close(cyc.id)
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        number = inv.number
        inv_id = inv.id
    return t, number, inv_id


@pytest.mark.asyncio
async def test_portal_invoices_roles_and_pdf(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t, number, inv_id = await _seed(session, app_session_factory)

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem cookie → 401
        assert (await c.get("/v1/invoices", headers=h)).status_code == 401
        # helpdesk → 403
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        assert (await c.get("/v1/invoices", headers=h)).status_code == 403

        # admin → lista só faturas do tenant
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "admin", st))
        lst = await c.get("/v1/invoices", headers=h)
        assert lst.status_code == 200
        rows = lst.json()
        assert len(rows) == 1
        assert rows[0]["number"] == number
        assert rows[0]["status"] == "open"

        # detalhe com linhas
        det = await c.get(f"/v1/invoices/{number}", headers=h)
        assert det.status_code == 200
        assert len(det.json()["lines"]) >= 1

        # guard numérico
        assert (await c.get("/v1/invoices/abc", headers=h)).status_code == 404

        # pdf on-demand → application/pdf + %PDF-
        pdf = await c.get(f"/v1/invoices/{number}/pdf", headers=h)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:5] == b"%PDF-"

    # pdf foi persistido (cache)
    async with db.tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await s.get(Invoice, inv_id)
        assert inv.pdf_bytes is not None
        assert inv.pdf_generated_at is not None
