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
    ConsumptionEvent,
    Contract,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_dashboard_balances_and_low_alerts(engine, app_session_factory, session, monkeypatch):
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
    # hour_bank 10h, consume 9.5h -> remaining 0.5h = 5% -> warning
    hb = Contract(
        tenant_id=a.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=10,
        unit_price_brl=100,
        created_by="seed",
    )
    # credit_brl 1000, consume 1000 -> remaining 0 = critical
    cr = Contract(
        tenant_id=a.id,
        code="CR",
        type=ContractType.credit_brl,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=1000,
        unit_price_brl=100,
        created_by="seed",
    )
    # closed_value -> NEVER alerts
    cv = Contract(
        tenant_id=a.id,
        code="CV",
        type=ContractType.closed_value,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=9000,
        unit_price_brl=9000,
        created_by="seed",
    )
    session.add_all([hb, cr, cv])
    await session.flush()
    session.add(
        ConsumptionEvent(
            contract_id=hb.id,
            occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref="r",
            billable_minutes=570,
            recorded_by="seed",
        )
    )  # 9.5h
    session.add(
        ConsumptionEvent(
            contract_id=cr.id,
            occurred_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref="r",
            billable_minutes=0,
            billable_amount_brl=1000,
            recorded_by="seed",
        )
    )
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
