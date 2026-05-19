"""Regressão #1F-a: resolução de tenant via X-Forwarded-Host (H9).

Fecha o gap que o e2e não pegava: o TestClient/httpx seta `Host` direto,
mas o portal Nuxt roda sobre undici (Node fetch), que PROÍBE override do
Host — encaminha o host do tenant via `X-Forwarded-Host`. Aqui provamos:

  (1) request com X-Forwarded-Host=aurora... e SEM Host usável
      (Host: sidecar:8001) resolve o tenant Aurora p/ /v1/branding
      (branded, não default);
  (2) o guard cross-tenant 403 continua valendo SOB XFH: gsid cunhado
      p/ Aurora apresentado com X-Forwarded-Host=technova... -> 403.
"""

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
async def test_xforwarded_host_resolves_tenant_and_cross_tenant_403(
    engine, app_session_factory, session, monkeypatch
):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    await seed_demo_contracts.seed(session)
    await session.commit()
    await seed_demo_branding.seed(session)
    await session.commit()

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # (1) XFH=aurora..., Host inútil (autoridade interna do sidecar):
        # resolve Aurora -> branding branded, NÃO o default neutro.
        ba = await c.get(
            "/v1/branding",
            headers={
                "host": "sidecar:8001",
                "x-forwarded-host": "aurora.suporte.gerti.com.br",
            },
        )
        assert ba.status_code == 200
        assert ba.json()["display_name"] == "Aurora Móveis"

        async def good(login, password):
            return True

        monkeypatch.setattr(auth_router, "authenticate_customer", good)

        # Login Aurora via XFH -> gsid cunhado p/ Aurora.
        la = await c.post(
            "/v1/auth/login",
            headers={
                "host": "sidecar:8001",
                "x-forwarded-host": "aurora.suporte.gerti.com.br",
            },
            json={"username": "eduardo.salvi", "password": "pw"},
        )
        assert la.status_code == 200
        cookie_a = c.cookies.get("gsid")
        assert cookie_a is not None

        # (2) Guard cross-tenant 403 vale SOB XFH: gsid Aurora apresentado
        # com X-Forwarded-Host=technova... -> 403 (session.tenant_id !=
        # tenant resolvido). Defesa de DADO inalterada.
        c.cookies.clear()
        c.cookies.set("gsid", cookie_a)
        xtenant = await c.get(
            "/v1/contracts",
            headers={
                "host": "sidecar:8001",
                "x-forwarded-host": "technova.suporte.gerti.com.br",
            },
        )
        assert xtenant.status_code == 403


@pytest.mark.asyncio
async def test_was_dev_br_subdomain_resolves_aurora_branding(
    engine, app_session_factory, session, monkeypatch
):
    """#1F-a: *.suporte.was.dev.br (zona CF do token de teste) deve resolver
    o mesmo tenant que *.suporte.gerti.com.br — o SUBDOMAIN_RE aceita ambas
    as bases via alternação ancorada."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    await seed_demo_contracts.seed(session)
    await session.commit()
    await seed_demo_branding.seed(session)
    await session.commit()

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # S1: XFH=aurora.suporte.was.dev.br → tenant Aurora → branding branded.
        resp = await c.get(
            "/v1/branding",
            headers={
                "host": "sidecar:8001",
                "x-forwarded-host": "aurora.suporte.was.dev.br",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Aurora Móveis"

        # Guard: host completamente desconhecido (não é *.suporte.gerti.com.br
        # nem *.suporte.was.dev.br) → o middleware extrai subdomain=None para
        # hosts sem padrão reconhecido OU, para hosts com subdomínio em base
        # desconhecida, não casa o regex → 404.
        resp_unknown = await c.get(
            "/v1/branding",
            headers={
                "host": "sidecar:8001",
                "x-forwarded-host": "aurora.suporte.evil.example.com",
            },
        )
        assert resp_unknown.status_code == 404
