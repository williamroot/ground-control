"""GET /v1/contracts/{id}/consumption: order, pagination, glosa, counts_toward_balance, 404."""

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
async def test_consumption_paginated_and_glosa(engine, app_session_factory, session, monkeypatch):
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
    session.add(TenantBranding(tenant_id=a.id, display_name="Aurora Móveis"))
    c = Contract(
        tenant_id=a.id,
        code="AUR-HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        unit_price_brl=180,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    evs = []
    for i, m in enumerate((60, 90, 120)):
        ev = ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"r{i}",
            billable_minutes=m,
            recorded_by="seed",
        )
        session.add(ev)
        await session.flush()
        evs.append(ev)
    # approved glosa on the FIRST (oldest) event; pending on the second.
    approved = Glosa(
        consumption_event_id=evs[0].id,
        status=GlosaStatus.approved,
        reason="x",
        requested_by="seed",
    )
    session.add(approved)
    pending = Glosa(
        consumption_event_id=evs[1].id,
        status=GlosaStatus.pending,
        reason="y",
        requested_by="seed",
    )
    session.add(pending)
    await session.flush()
    # H15: set the app-layer back-pointer (consumption_event.glosa_id, no FK) so
    # the consumption query's outerjoin (Glosa.id == ConsumptionEvent.glosa_id)
    # resolves each event's glosa. For the approved one this ALSO makes
    # counts_toward_balance agree with balance()'s glosa_id-based exclusion
    # (glosa_id IN approved -> excluded). The pending one is surfaced but still
    # counts (pending is not in the approved set), matching balance().
    evs[0].glosa_id = approved.id
    evs[1].glosa_id = pending.id
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
        url = f"/v1/contracts/{c.id}/consumption"
        p1 = (await cl.get(f"{url}?page=1&page_size=2", headers=ha)).json()
        assert len(p1["items"]) == 2 and p1["page"] == 1
        p2 = (await cl.get(f"{url}?page=2&page_size=2", headers=ha)).json()
        assert len(p2["items"]) == 1


@pytest.mark.asyncio
async def test_consumption_404_cross_tenant(engine, app_session_factory, session, monkeypatch):
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
    b = Tenant(
        legal_name="Tech",
        trade_name="Tech",
        document="2",
        znuny_customer_id="TECH",
        znuny_instance_id=inst.id,
        subdomain="technova",
    )
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            TenantBranding(tenant_id=a.id, display_name="A"),
            TenantBranding(tenant_id=b.id, display_name="T"),
        ]
    )
    c = Contract(
        tenant_id=a.id,
        code="AUR-HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        created_by="seed",
    )
    session.add(c)
    await session.commit()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        cl.cookies.set("gsid", encode_session(str(b.id), "x", st))
        xr = await cl.get(
            f"/v1/contracts/{c.id}/consumption",
            headers={"host": "technova.suporte.gerti.com.br"},
        )
        assert xr.status_code == 404
