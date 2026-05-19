"""GET /v1/branding: subdomain-scoped, no auth, 404 on root/unknown host.

Mirrors test_tenant_middleware.py: the subdomain->tenant resolution path
is bound to the admin `engine` (BYPASSRLS) via db.AdminSessionLocal so the
FORCE-RLS gerti.tenant lookup succeeds; the tenant DATA path
(db.SessionLocal=app_session_factory) stays RLS-subject and is exercised
under the app.current_tenant GUC set by tenant_session_scope.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@pytest.mark.asyncio
async def test_branding_resolves_by_subdomain_and_404_on_root(
    engine, app_session_factory, session, monkeypatch
):
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
        TenantBranding(
            tenant_id=t.id,
            display_name="Aurora Móveis",
            primary_color="#0EA5E9",
            support_email="suporte@aurora.example",
        )
    )
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
        ok = await c.get("/v1/branding", headers={"host": "aurora.suporte.gerti.com.br"})
        assert ok.status_code == 200
        body = ok.json()
        assert body["display_name"] == "Aurora Móveis"
        assert body["primary_color"] == "#0EA5E9"
        assert body["support_email"] == "suporte@aurora.example"

        root = await c.get("/v1/branding", headers={"host": "localhost"})
        assert root.status_code == 404
