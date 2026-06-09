"""GET /v1/admin/analytics?tenant_id= (#1O): agente (gsid_adm) -> 200;
tenant_id inválido/desconhecido -> 404; sem sessão -> 401. Mesma agregação
do portal, mas cross-tenant (console)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_ticket import TicketStats
from gerti_sidecar.main import create_app
from gerti_sidecar.models import (
    Contract,
    CsatResponse,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_admin_analytics(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
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
    a = Tenant(
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(a)
    await session.flush()
    session.add(TenantBranding(tenant_id=a.id, display_name="A"))
    session.add(
        Contract(
            tenant_id=a.id,
            code="HB",
            type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_hours=10,
            unit_price_brl=100,
            created_by="seed",
        )
    )
    session.add(CsatResponse(tenant_id=a.id, znuny_ticket_id=11, customer_login="joe", score=4))
    await session.commit()

    async def fake_stats(*, customer_id, since, until):
        assert customer_id == "AURORA"
        return TicketStats(
            by_state={"open": 5},
            by_priority={},
            by_day=[],
            sla_breached=0,
            sla_at_risk=2,
            total=5,
        )

    monkeypatch.setattr(znuny_ticket, "ticket_stats", fake_stats)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        # sem sessão -> 401
        assert (await cl.get(f"/v1/admin/analytics?tenant_id={a.id}")).status_code == 401
        cl.cookies.set("gsid_adm", encode_admin_session("william", st))
        # tenant_id mal-formado -> 404
        assert (await cl.get("/v1/admin/analytics?tenant_id=not-a-uuid")).status_code == 404
        # tenant_id desconhecido -> 404
        assert (await cl.get(f"/v1/admin/analytics?tenant_id={uuid.uuid4()}")).status_code == 404
        # tenant válido -> 200
        r = await cl.get(f"/v1/admin/analytics?tenant_id={a.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["csat"]["count"] == 1
        assert body["tickets"]["sla_at_risk"] == 2
        assert body["balance"]["contract_count"] == 1
