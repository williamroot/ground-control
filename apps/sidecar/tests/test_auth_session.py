"""JWT session: encode/decode, /v1/me, no-tenant 401, wrong-tenant 403."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@pytest.mark.asyncio
async def test_me_requires_matching_tenant(engine, app_session_factory, session, monkeypatch):
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
    st = get_settings()
    good = encode_session(str(t.id), "joe", "admin", st)
    bad = encode_session("00000000-0000-0000-0000-000000000000", "x", "admin", st)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        h = {"host": "aurora.suporte.gerti.com.br"}
        assert (await c.get("/v1/me", headers=h)).status_code == 401
        c.cookies.set("gsid", bad)
        assert (await c.get("/v1/me", headers=h)).status_code == 403
        c.cookies.set("gsid", good)
        ok = await c.get("/v1/me", headers=h)
        assert ok.status_code == 200
        assert ok.json()["customer_login"] == "joe"
        assert ok.json()["display_name"] == "Aurora Móveis"
