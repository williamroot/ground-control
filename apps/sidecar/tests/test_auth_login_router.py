"""POST /v1/auth/login: 200+cookie ok, 401 bad cred, 503 Znuny down; logout."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.routers import auth as auth_router


@pytest.mark.asyncio
async def test_login_paths(engine, app_session_factory, session, monkeypatch):
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
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
    await session.commit()
    # Resolution path = admin engine (BYPASSRLS, mirrors
    # test_tenant_middleware.py); data path = RLS-subject (gerti_sidecar).
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    h = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)

    async def good(login, password):
        return True

    async def bad(login, password):
        return False

    async def down(login, password):
        raise auth_router.ZnunyUnavailable("down")

    async with AsyncClient(transport=transport, base_url="http://t") as c:
        monkeypatch.setattr(auth_router, "authenticate_customer", good)
        r = await c.post("/v1/auth/login", headers=h, json={"username": "joe", "password": "pw"})
        assert r.status_code == 200
        assert "gsid" in r.cookies
        monkeypatch.setattr(auth_router, "authenticate_customer", bad)
        assert (
            await c.post("/v1/auth/login", headers=h, json={"username": "x", "password": "y"})
        ).status_code == 401
        monkeypatch.setattr(auth_router, "authenticate_customer", down)
        assert (
            await c.post("/v1/auth/login", headers=h, json={"username": "x", "password": "y"})
        ).status_code == 503
        out = await c.post("/v1/auth/logout", headers=h)
        assert out.status_code == 204
