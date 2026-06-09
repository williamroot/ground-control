"""GET /v1/dashboard/metrics (#1O): admin do tenant -> 200 com blocos;
helpdesk -> 403; sem sessão -> 401. CSAT/saldo do Postgres tenant-scoped,
tickets via GI (mockado)."""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
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
async def test_dashboard_metrics(engine, app_session_factory, session, monkeypatch):
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
    session.add(CsatResponse(tenant_id=a.id, znuny_ticket_id=11, customer_login="joe", score=5))
    await session.commit()

    async def fake_stats(*, customer_id, since, until):
        assert customer_id == "AURORA"
        return TicketStats(
            by_state={"open": 2},
            by_priority={"3 normal": 2},
            by_day=[{"date": "2026-06-01", "count": 2}],
            sla_breached=1,
            sla_at_risk=0,
            total=2,
        )

    monkeypatch.setattr(znuny_ticket, "ticket_stats", fake_stats)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    ha = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        # sem sessão -> 401
        assert (await cl.get("/v1/dashboard/metrics", headers=ha)).status_code == 401
        # helpdesk -> 403
        cl.cookies.set("gsid", encode_session(str(a.id), "joe", "helpdesk", st))
        assert (await cl.get("/v1/dashboard/metrics", headers=ha)).status_code == 403
        # admin -> 200 com blocos
        cl.cookies.set("gsid", encode_session(str(a.id), "joe", "admin", st))
        r = await cl.get("/v1/dashboard/metrics", headers=ha)
        assert r.status_code == 200
        body = r.json()
        assert body["csat"]["count"] == 1
        assert body["csat"]["avg"] == 5.0
        assert body["tickets"]["sla_breached"] == 1
        assert body["balance"]["contract_count"] == 1
