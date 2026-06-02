"""Spec #1H — papéis no portal: resolução, default least-privilege, RLS,
require_admin (admin 200 / helpdesk 403 / sem sessão 401), /me com role e o
caminho de login resolvendo o papel.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth import session as sess
from gerti_sidecar.config import get_settings
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.portal_role_service import resolve_role
from gerti_sidecar.main import create_app
from gerti_sidecar.models import PortalUserRole, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import PortalRole

AURORA_ADMIN = "eduardo.salvi@auroramoveis.com.br"
AURORA_HELPDESK = "helpdesk@auroramoveis.com.br"


async def _seed_two(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
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
        legal_name="Beta",
        trade_name="Beta",
        document="2",
        znuny_customer_id="BETA",
        znuny_instance_id=inst.id,
        subdomain="beta",
    )
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            TenantBranding(tenant_id=a.id, display_name="Aurora Móveis"),
            TenantBranding(tenant_id=b.id, display_name="Beta"),
            # papel mapeado só na Aurora; o e-mail helpdesk e o não-mapeado caem no default
            PortalUserRole(tenant_id=a.id, customer_login=AURORA_ADMIN, role=PortalRole.admin),
            PortalUserRole(
                tenant_id=a.id, customer_login=AURORA_HELPDESK, role=PortalRole.helpdesk
            ),
        ]
    )
    await session.commit()
    return a.id, b.id


@pytest.mark.asyncio
async def test_resolve_role_default_and_rls(engine, app_session_factory, session, monkeypatch):
    aurora_id, beta_id = await _seed_two(session)

    async with tenant_session_scope(aurora_id, factory=app_session_factory) as s:
        assert await resolve_role(s, AURORA_ADMIN) == PortalRole.admin
        # case-insensitive (casa com lower() dos dois lados)
        assert await resolve_role(s, AURORA_ADMIN.upper()) == PortalRole.admin
        assert await resolve_role(s, AURORA_HELPDESK) == PortalRole.helpdesk
        # não-mapeado ⇒ helpdesk (least-privilege)
        assert await resolve_role(s, "ghost@nope.com") == PortalRole.helpdesk

    # RLS: sob o tenant Beta, o mapeamento admin da Aurora NÃO é visível ⇒ helpdesk
    async with tenant_session_scope(beta_id, factory=app_session_factory) as s:
        assert await resolve_role(s, AURORA_ADMIN) == PortalRole.helpdesk


@pytest.mark.asyncio
async def test_decode_session_without_role_defaults_helpdesk(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    get_settings.cache_clear()
    st = get_settings()
    exp = int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp())
    # token legado SEM o claim role
    legacy = jwt.encode(
        {"tenant_id": str(uuid.uuid4()), "customer_login": "joe", "exp": exp},
        st.session_secret,
        algorithm="HS256",
    )
    payload = sess.decode_session(legacy, st)
    assert payload is not None
    assert payload["role"] == PortalRole.helpdesk.value


@pytest.mark.asyncio
async def test_require_admin_gating(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    aurora_id, _ = await _seed_two(session)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        admin_tok = sess.encode_session(str(aurora_id), AURORA_ADMIN, "admin", st)
        help_tok = sess.encode_session(str(aurora_id), AURORA_HELPDESK, "helpdesk", st)

        # sem sessão -> 401 nos endpoints admin
        assert (await cl.get("/v1/contracts", headers=h)).status_code == 401
        assert (await cl.get("/v1/dashboard", headers=h)).status_code == 401

        # admin -> 200 (lista vazia, mas autorizado)
        cl.cookies.set("gsid", admin_tok)
        assert (await cl.get("/v1/contracts", headers=h)).status_code == 200
        assert (await cl.get("/v1/dashboard", headers=h)).status_code == 200
        me_admin = (await cl.get("/v1/me", headers=h)).json()
        assert me_admin["role"] == "admin"

        # help-desk -> 403 forbidden_role nos endpoints admin, mas /me 200 com role
        cl.cookies.clear()
        cl.cookies.set("gsid", help_tok)
        r_contracts = await cl.get("/v1/contracts", headers=h)
        assert r_contracts.status_code == 403
        assert r_contracts.json()["detail"] == "forbidden_role"
        assert (await cl.get("/v1/dashboard", headers=h)).status_code == 403
        me_help = (await cl.get("/v1/me", headers=h)).json()
        assert me_help["role"] == "helpdesk"


@pytest.mark.asyncio
async def test_login_resolves_role_into_cookie(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    aurora_id, _ = await _seed_two(session)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    from gerti_sidecar.routers import auth as auth_router

    async def ok(login: str, password: str) -> bool:
        return True

    monkeypatch.setattr(auth_router, "authenticate_customer", ok)
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)

    def role_of(token: str) -> str:
        return sess.decode_session(token, st)["role"]  # type: ignore[index]

    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        # admin mapeado -> cookie role=admin
        r = await cl.post(
            "/v1/auth/login", headers=h, json={"username": AURORA_ADMIN, "password": "x"}
        )
        assert r.status_code == 200
        assert role_of(r.cookies["gsid"]) == "admin"

        # help-desk mapeado -> role=helpdesk
        cl.cookies.clear()
        r = await cl.post(
            "/v1/auth/login", headers=h, json={"username": AURORA_HELPDESK, "password": "x"}
        )
        assert role_of(r.cookies["gsid"]) == "helpdesk"

        # não-mapeado -> default helpdesk
        cl.cookies.clear()
        r = await cl.post(
            "/v1/auth/login", headers=h, json={"username": "ghost@x.com", "password": "x"}
        )
        assert role_of(r.cookies["gsid"]) == "helpdesk"
