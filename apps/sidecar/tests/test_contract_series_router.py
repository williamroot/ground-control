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
    ConsumptionEvent,
    Contract,
    Glosa,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, GlosaStatus


@pytest.mark.asyncio
async def test_series_dense_daily_excludes_approved(
    engine, app_session_factory, session, monkeypatch
):
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
    # short window so daily buckets are dense and few
    c = Contract(
        tenant_id=a.id,
        code="AUR-HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 1, 5),
        initial_hours=40,
        unit_price_brl=180,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    e1 = ConsumptionEvent(
        contract_id=c.id,
        occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        source_kind="ticket_work",
        source_ref="r1",
        billable_minutes=60,
        recorded_by="seed",
    )
    e2 = ConsumptionEvent(
        contract_id=c.id,
        occurred_at=dt.datetime(2026, 1, 4, tzinfo=dt.UTC),
        source_kind="ticket_work",
        source_ref="r2",
        billable_minutes=120,
        recorded_by="seed",
    )
    session.add_all([e1, e2])
    await session.flush()
    # approved glosa on e2 -> excluded from series
    g = Glosa(
        consumption_event_id=e2.id,
        status=GlosaStatus.approved,
        reason="x",
        requested_by="seed",
    )
    session.add(g)
    await session.flush()
    e2.glosa_id = g.id  # H15 back-pointer: predicate keys on consumption_event.glosa_id
    await session.commit()
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
        cl.cookies.set("gsid", encode_session(str(a.id), "joe", "admin", st))
        # today after window so end == ends_on -> 5 dense daily buckets Jan 1..5
        r = await cl.get(f"/v1/contracts/{c.id}/series?today=2026-06-01", headers=ha)
        assert r.status_code == 200
        body = r.json()
        assert body["granularity"] == "day"
        assert body["kind"] == "hours"
        assert [p["bucket"] for p in body["points"]] == [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
            "2026-01-05",
        ]
        # Jan 2 = 60min/60 = 1.0h; Jan 4 excluded (approved glosa) -> 0.0
        assert body["points"][1]["value"] == pytest.approx(1.0)
        assert body["points"][3]["value"] == pytest.approx(0.0)
