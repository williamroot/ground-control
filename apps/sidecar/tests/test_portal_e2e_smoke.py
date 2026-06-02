"""E2E smoke (#1F-a): prova de isolamento white-label cross-tenant.

seed #1C (Aurora tenant+6 contratos) + seed_demo_branding (Aurora branding
+ tenant TechNova + branding + 2 contratos) -> branding DIFERENTE por
subdomínio -> login (Znuny mockado) por tenant -> /v1/contracts só do
tenant da sessão -> cookie do tenant A no subdomínio B = 403."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.routers import auth as auth_router

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seed_demo_branding  # noqa: E402
import seed_demo_contracts  # noqa: E402


@pytest.mark.asyncio
async def test_portal_vertical_slice_two_tenants(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    await seed_demo_contracts.seed(session)
    await session.commit()
    aurora_id, technova_id = await seed_demo_branding.seed(session)
    await session.commit()

    # Resolution path = admin engine (BYPASSRLS, mirrors
    # test_tenant_middleware.py); data path = RLS-subject (gerti_sidecar)
    # via db.SessionLocal -> get_tenant_session -> tenant_session_scope.
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    h_a = {"host": "aurora.suporte.gerti.com.br"}
    h_t = {"host": "technova.suporte.gerti.com.br"}

    async def good(login, password):
        return True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # (1) Branding resolves DIFFERENTLY per subdomain.
        ba = await c.get("/v1/branding", headers=h_a)
        bt = await c.get("/v1/branding", headers=h_t)
        assert ba.status_code == 200 and bt.status_code == 200
        assert ba.json()["display_name"] == "Aurora Móveis"
        assert bt.json()["display_name"] == "TechNova"
        assert ba.json()["primary_color"] != bt.json()["primary_color"]

        monkeypatch.setattr(auth_router, "authenticate_customer", good)

        # (2a) Aurora session sees ONLY Aurora's 6 contracts.
        # Login sempre por e-mail; o e-mail admin resolve role=admin (Spec #1H)
        # via o portal_user_role semeado por seed_demo_branding.
        la = await c.post(
            "/v1/auth/login",
            headers=h_a,
            json={"username": "eduardo.salvi@auroramoveis.com.br", "password": "pw"},
        )
        assert la.status_code == 200
        cookie_a = c.cookies.get("gsid")
        assert cookie_a is not None
        ca = await c.get("/v1/contracts", headers=h_a)
        assert ca.status_code == 200
        assert len(ca.json()) == 6

        # (2b) TechNova session sees ONLY TechNova's 2 contracts.
        c.cookies.clear()
        lt = await c.post(
            "/v1/auth/login",
            headers=h_t,
            json={"username": "admin.tech@technova.example", "password": "pw"},
        )
        assert lt.status_code == 200
        cookie_t = c.cookies.get("gsid")
        assert cookie_t is not None
        ct = await c.get("/v1/contracts", headers=h_t)
        assert ct.status_code == 200
        assert len(ct.json()) == 2

        # (3) gsid minted for Aurora presented on TechNova's subdomain
        # -> rejected 403 (get_current_session cross-tenant guard).
        c.cookies.clear()
        c.cookies.set("gsid", cookie_a)
        xtenant = await c.get("/v1/contracts", headers=h_t)
        assert xtenant.status_code == 403
        # ...and TechNova's cookie on Aurora's subdomain is also 403.
        c.cookies.clear()
        c.cookies.set("gsid", cookie_t)
        xtenant2 = await c.get("/v1/contracts", headers=h_a)
        assert xtenant2.status_code == 403
