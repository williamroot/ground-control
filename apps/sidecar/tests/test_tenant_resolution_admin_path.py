"""TenantMiddleware resolves subdomain via a BYPASSRLS path; data stays RLS.

AdminSessionLocal (admin engine, BYPASSRLS) resolves the subdomain ->
Tenant directory lookup; the route's tenant_session_scope data session
stays RLS-subject (gerti_sidecar) and is still fail-closed without GUC.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@pytest.mark.asyncio
async def test_tenant_resolution_uses_admin_path(engine, app_session_factory, session, monkeypatch):
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

    # Resolution path = admin engine (BYPASSRLS); data path = RLS-subject.
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # valid subdomain resolves (200-class, NOT 404) because the
        # directory lookup goes through the BYPASSRLS path
        ok = await c.get("/v1/branding", headers={"host": "aurora.suporte.gerti.com.br"})
        assert ok.status_code == 200
        assert ok.json()["display_name"] == "Aurora Móveis"

    # RLS still fail-closed on tenant DATA without the GUC (proves the
    # narrow path did NOT widen the data plane).
    async with app_session_factory() as s:
        rows = (
            (await s.execute(text("SELECT display_name FROM gerti.tenant_branding")))
            .scalars()
            .all()
        )
    assert rows == []
