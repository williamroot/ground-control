"""GET/PUT /v1/admin/tenants/{id}/branding — identidade visual editável (Spec #3 V4).

- PUT válido → 200 e persiste
- cor fora do formato hex → 422
- logo_url http:// (não https) → 422
- tenant inexistente → 404
- leitura pública GET /v1/branding continua intacta após a edição do console
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_tenant(session) -> uuid.UUID:
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
        legal_name="Aurora SA",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora-brand",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora"))
    await session.commit()
    return t.id


def _wire(monkeypatch, engine, app_session_factory) -> None:
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


_VALID_BODY = {
    "display_name": "Aurora Móveis",
    "primary_color": "#0EA5E9",
    "accent_color": "#0369A1",
    "logo_url": "https://cdn.example.com/logo.png",
    "default_theme": "system",
}


@pytest.mark.asyncio
async def test_put_branding_valid_then_public_read_reflects_it(
    engine, app_session_factory, session, monkeypatch
):
    st = _settings(monkeypatch)
    tid = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        put = await c.put(f"/v1/admin/tenants/{tid}/branding", headers=_HOST, json=_VALID_BODY)
        assert put.status_code == 200, put.text
        assert put.json()["display_name"] == "Aurora Móveis"
        assert put.json()["default_theme"] == "system"

        get = await c.get(f"/v1/admin/tenants/{tid}/branding", headers=_HOST)
        assert get.status_code == 200
        assert get.json()["primary_color"] == "#0EA5E9"

        # leitura pública (sem sessão) continua intacta e reflete a edição.
        public = await c.get("/v1/branding", headers={"host": "aurora-brand.suporte.gerti.com.br"})
        assert public.status_code == 200
        assert public.json()["display_name"] == "Aurora Móveis"
        assert public.json()["default_theme"] == "system"


@pytest.mark.asyncio
async def test_put_branding_invalid_color_is_422(engine, app_session_factory, session, monkeypatch):
    st = _settings(monkeypatch)
    tid = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory)

    body = dict(_VALID_BODY, primary_color="blue")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(f"/v1/admin/tenants/{tid}/branding", headers=_HOST, json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_branding_http_logo_url_is_422(engine, app_session_factory, session, monkeypatch):
    st = _settings(monkeypatch)
    tid = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory)

    body = dict(_VALID_BODY, logo_url="http://cdn.example.com/logo.png")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(f"/v1/admin/tenants/{tid}/branding", headers=_HOST, json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_branding_nonexistent_tenant_is_404(
    engine, app_session_factory, session, monkeypatch
):
    st = _settings(monkeypatch)
    await _seed_tenant(session)  # algum tenant existe, mas não o alvo
    _wire(monkeypatch, engine, app_session_factory)

    ghost = uuid.uuid4()
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(f"/v1/admin/tenants/{ghost}/branding", headers=_HOST, json=_VALID_BODY)
    assert r.status_code == 404
    assert r.json()["detail"] == "tenant_not_found"


@pytest.mark.asyncio
async def test_branding_requires_admin_session(engine, app_session_factory, session, monkeypatch):
    _settings(monkeypatch)
    tid = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get(f"/v1/admin/tenants/{tid}/branding", headers=_HOST)
    assert r.status_code == 401
