"""Spec #1K Fase 2 Task 4 — router /v1/assets*.

Verifica: 401 sem sessão; helpdesk logado recebe lista; escopo server-trusted
(customer_id vem do tenant, não do cliente); anti-IDOR (ZnunyWriteError → 404).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@pytest.mark.asyncio
async def test_assets_scoped_by_tenant(engine, app_session_factory, session, monkeypatch):
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
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora"))
    await session.commit()

    captured: dict[str, object] = {}

    async def fake_search(*, customer_id: str) -> list[znuny_ticket.AssetSummary]:
        captured["cid"] = customer_id
        return [
            znuny_ticket.AssetSummary(
                id=5,
                number="10001",
                class_="Computer",
                name="PC-001",
                deploy_state="Production",
                inci_state="Operational",
            )
        ]

    monkeypatch.setattr(znuny_ticket, "config_item_search", fake_search)
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
        # 401 without session
        assert (await c.get("/v1/assets", headers=h)).status_code == 401

        # helpdesk session gets assets
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/assets", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert data[0]["name"] == "PC-001"
        assert data[0]["znuny_config_item_id"] == 5
        assert data[0]["class_"] == "Computer"
        # escopo server-trusted: customer_id vem do tenant
        assert captured["cid"] == "AURORA"


@pytest.mark.asyncio
async def test_asset_detail_not_found(engine, app_session_factory, session, monkeypatch):
    """ZnunyWriteError (not found / IDOR) -> 404."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    inst = ZnunyInstance(
        name="i2",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Beta",
        trade_name="Beta",
        document="2",
        znuny_customer_id="BETA",
        znuny_instance_id=inst.id,
        subdomain="beta",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Beta"))
    await session.commit()

    async def fake_get(*, config_item_id: int, customer_id: str) -> znuny_ticket.AssetDetail:
        raise ZnunyWriteError("not found")

    monkeypatch.setattr(znuny_ticket, "config_item_get", fake_get)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "beta.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/assets/999", headers=h)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_asset_detail_unavailable(engine, app_session_factory, session, monkeypatch):
    """ZnunyUnavailable -> 503."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    inst = ZnunyInstance(
        name="i3",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Gamma",
        trade_name="Gamma",
        document="3",
        znuny_customer_id="GAMMA",
        znuny_instance_id=inst.id,
        subdomain="gamma",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Gamma"))
    await session.commit()

    async def fake_get(*, config_item_id: int, customer_id: str) -> znuny_ticket.AssetDetail:
        raise ZnunyUnavailable("down")

    monkeypatch.setattr(znuny_ticket, "config_item_get", fake_get)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "gamma.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/assets/5", headers=h)
        assert r.status_code == 503
