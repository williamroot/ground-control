"""POST /v1/auth/login: cookie gsid deve conter claim znuny_login canônico (Spec #1F).

Mock authenticate_customer→True e resolve_login_from_email→'eduardo.salvi'.
POST /v1/auth/login com username='eduardo.salvi@auroramoveis.com.br'.
Assert: customer_login == e-mail original; znuny_login == 'eduardo.salvi'.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import decode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.routers import auth as auth_router


@pytest.mark.asyncio
async def test_login_cookie_carries_znuny_login(engine, app_session_factory, session, monkeypatch):
    """gsid emitido no login deve conter customer_login=email E znuny_login=login_curto."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    # Seed tenant Aurora
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
        legal_name="Aurora Móveis",
        trade_name="Aurora Móveis",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
    await session.commit()

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    h = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)

    async def _authenticate_ok(login, password):
        return True

    async def _resolve_short(email):
        # Simula a resolução: email → login curto do Znuny
        return "eduardo.salvi"

    monkeypatch.setattr(auth_router, "authenticate_customer", _authenticate_ok)
    monkeypatch.setattr(auth_router, "resolve_login_from_email", _resolve_short)

    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/auth/login",
            headers=h,
            json={"username": "eduardo.salvi@auroramoveis.com.br", "password": "senha"},
        )
        assert r.status_code == 200
        assert "gsid" in r.cookies

        st = get_settings()
        cookie_value = r.cookies["gsid"]
        payload = decode_session(cookie_value, st)
        assert payload is not None

        # customer_login deve ser o e-mail original (usado para resolve_role)
        assert payload["customer_login"] == "eduardo.salvi@auroramoveis.com.br"
        # znuny_login deve ser o login canônico curto do Znuny
        assert payload["znuny_login"] == "eduardo.salvi"


@pytest.mark.asyncio
async def test_login_non_email_znuny_login_equals_username(
    engine, app_session_factory, session, monkeypatch
):
    """Login sem '@': znuny_login == customer_login == username (sem DB lookup)."""
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
        legal_name="TechNova",
        trade_name="TechNova",
        document="2",
        znuny_customer_id="TECHNOVA",
        znuny_instance_id=inst.id,
        subdomain="technova",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="TechNova"))
    await session.commit()

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    h = {"host": "technova.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)

    async def _authenticate_ok(login, password):
        return True

    # resolve_login_from_email NÃO deve ser chamado para username sem '@'.
    def _resolve_must_not_be_called(email):  # pragma: no cover
        raise AssertionError("resolve_login_from_email não deve ser chamado para login sem '@'")

    monkeypatch.setattr(auth_router, "authenticate_customer", _authenticate_ok)
    monkeypatch.setattr(auth_router, "resolve_login_from_email", _resolve_must_not_be_called)

    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/auth/login",
            headers=h,
            json={"username": "admin.tech", "password": "pw"},
        )
        assert r.status_code == 200
        assert "gsid" in r.cookies

        st = get_settings()
        payload = decode_session(r.cookies["gsid"], st)
        assert payload is not None
        assert payload["customer_login"] == "admin.tech"
        assert payload["znuny_login"] == "admin.tech"
