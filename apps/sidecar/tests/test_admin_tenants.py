"""/v1/admin/tenants*: onboarding (GI + tenant/branding/papéis), idempotência, detalhe.

Cross-tenant via AdminSessionLocal (BYPASSRLS, D16). As 3 funções GI de escrita
são monkeypatched (sem Znuny real — fiação real é T1.B/Fase 2). Cookie admin via
encode_admin_session.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.main import create_app
from gerti_sidecar.models import (
    Contract,
    PortalUserRole,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, PortalRole

_HOST = {"host": "gerti.was.dev.br"}  # host admin → bypass do TenantMiddleware


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


def _wire_admin_db(monkeypatch: pytest.MonkeyPatch, engine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)


class _GISpy:
    """Captura as chamadas GI monkeypatched (3 funções de escrita)."""

    def __init__(self) -> None:
        self.companies: list[tuple[str, str]] = []
        self.users: list[dict[str, str]] = []
        self.passwords: list[tuple[str, str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _company(customer_id, company_name, *, valid=True):
            self.companies.append((customer_id, company_name))
            return customer_id

        async def _user(*, login, email, first_name, last_name, customer_id, valid=True):
            self.users.append(
                {
                    "login": login,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "customer_id": customer_id,
                }
            )
            return login

        async def _password(login, password):
            self.passwords.append((login, password))

        monkeypatch.setattr(gi, "create_customer_company", _company)
        monkeypatch.setattr(gi, "create_customer_user", _user)
        monkeypatch.setattr(gi, "set_password", _password)


async def _seed_instance(session: AsyncSession) -> ZnunyInstance:
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.commit()
    return inst


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _admin_cookie(settings) -> str:
    return encode_admin_session("william", settings)


def _onboard_body(*, customer="ACME", subdomain="acme") -> dict:
    return {
        "legal_name": "Acme Indústria Ltda.",
        "trade_name": "Acme",
        "document": "11.111.111/0001-11",
        "subdomain": subdomain,
        "znuny_customer_id": customer,
        "branding": {
            "display_name": "Acme",
            "primary_color": "#123456",
            "accent_color": "#654321",
            "support_email": "suporte@acme.example",
            "logo_url": "https://cdn.acme.example/logo.svg",
        },
        "users": [
            {
                "email": "Admin@Acme.Example",
                "first_name": "Ana",
                "last_name": "Admin",
                "password": "s3cret-pw",
                "role": "admin",
            },
            {
                "email": "help@acme.example",
                "first_name": "Hugo",
                "last_name": "Help",
                "password": "help-pw",
                "role": "helpdesk",
            },
        ],
    }


@pytest.mark.asyncio
async def test_onboarding_creates_tenant_branding_roles(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    spy = _GISpy()
    spy.install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        r = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["subdomain_to_register"] == "acme"
    assert sorted(out["created_users"]) == ["admin@acme.example", "help@acme.example"]
    assert out["tenant"]["trade_name"] == "Acme"
    assert {u["customer_login"]: u["role"] for u in out["tenant"]["users"]} == {
        "admin@acme.example": "admin",
        "help@acme.example": "helpdesk",
    }

    # GI foi chamado: 1 empresa, 2 usuários, 2 senhas.
    assert spy.companies == [("ACME", "Acme")]
    assert len(spy.users) == 2
    assert len(spy.passwords) == 2

    # Linhas no Postgres: tenant + branding + 2 papéis.
    tenant = (
        await session.execute(select(Tenant).where(Tenant.znuny_customer_id == "ACME"))
    ).scalar_one()
    branding = await session.get(TenantBranding, tenant.id)
    assert branding is not None
    assert branding.primary_color == "#123456"
    roles = (
        (await session.execute(select(PortalUserRole).where(PortalUserRole.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert {r.customer_login: r.role for r in roles} == {
        "admin@acme.example": PortalRole.admin,
        "help@acme.example": PortalRole.helpdesk,
    }


@pytest.mark.asyncio
async def test_onboarding_idempotent(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        r1 = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
        assert r1.status_code == 201
        r2 = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
        assert r2.status_code == 201

    # Não duplicou: 1 tenant, 1 branding, 2 papéis.
    n_tenants = (
        await session.execute(
            select(func.count()).select_from(Tenant).where(Tenant.znuny_customer_id == "ACME")
        )
    ).scalar_one()
    assert n_tenants == 1
    tenant = (
        await session.execute(select(Tenant).where(Tenant.znuny_customer_id == "ACME"))
    ).scalar_one()
    n_roles = (
        await session.execute(
            select(func.count())
            .select_from(PortalUserRole)
            .where(PortalUserRole.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert n_roles == 2


@pytest.mark.asyncio
async def test_onboarding_dup_subdomain_other_customer_conflicts(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        r1 = await c.post(
            "/v1/admin/tenants",
            headers=_HOST,
            json=_onboard_body(customer="ACME", subdomain="acme"),
        )
        assert r1.status_code == 201
        # MESMO subdomínio, cliente DIFERENTE → conflito limpo (4xx, não 500).
        r2 = await c.post(
            "/v1/admin/tenants",
            headers=_HOST,
            json=_onboard_body(customer="OTHER", subdomain="acme"),
        )
    assert r2.status_code == 409, r2.text
    assert "acme" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_list_detail_and_404(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        onboard = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
        assert onboard.status_code == 201
        tenant_id = onboard.json()["tenant"]["id"]

        # adiciona 2 contratos diretamente p/ exercitar contract_count.
        async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as s:
            import uuid as _uuid

            for code in ("C-1", "C-2"):
                s.add(
                    Contract(
                        tenant_id=_uuid.UUID(tenant_id),
                        code=code,
                        type=ContractType.credit_brl,
                        starts_on=dt.date(2026, 1, 1),
                        ends_on=dt.date(2026, 12, 31),
                        initial_amount_brl=1000,
                        created_by="t",
                    )
                )
            await s.commit()

        lst = await c.get("/v1/admin/tenants", headers=_HOST)
        assert lst.status_code == 200
        rows = lst.json()
        assert len(rows) == 1
        assert rows[0]["id"] == tenant_id
        assert rows[0]["contract_count"] == 2
        assert rows[0]["status"] == "active"

        det = await c.get(f"/v1/admin/tenants/{tenant_id}", headers=_HOST)
        assert det.status_code == 200
        body = det.json()
        assert body["branding"]["display_name"] == "Acme"
        assert len(body["users"]) == 2
        assert len(body["contracts"]) == 2

        # id inexistente → 404
        missing = await c.get(
            "/v1/admin/tenants/00000000-0000-0000-0000-000000000000", headers=_HOST
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_add_tenant_user(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    spy = _GISpy()
    spy.install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        onboard = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
        tenant_id = onboard.json()["tenant"]["id"]

        r = await c.post(
            f"/v1/admin/tenants/{tenant_id}/users",
            headers=_HOST,
            json={
                "email": "New.User@Acme.Example",
                "first_name": "Nina",
                "last_name": "Nova",
                "password": "pw",
                "role": "helpdesk",
            },
        )
    assert r.status_code == 201, r.text
    assert r.json() == {"customer_login": "new.user@acme.example", "role": "helpdesk"}
    # GI recebeu o novo usuário com o customer_id do tenant.
    assert any(
        u["customer_id"] == "ACME" and u["login"] == "New.User@Acme.Example" for u in spy.users
    )

    role = (
        await session.execute(
            select(PortalUserRole).where(
                func.lower(PortalUserRole.customer_login) == "new.user@acme.example"
            )
        )
    ).scalar_one()
    assert role.role == PortalRole.helpdesk


@pytest.mark.asyncio
async def test_all_endpoints_require_admin_session(engine, session, monkeypatch):
    _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:  # SEM cookie gsid_adm
        for method, path in [
            ("GET", "/v1/admin/tenants"),
            ("POST", "/v1/admin/tenants"),
            ("GET", "/v1/admin/tenants/abc"),
            ("POST", "/v1/admin/tenants/abc/users"),
        ]:
            r = await c.request(method, path, headers=_HOST, json={})
            assert r.status_code == 401, (method, path, r.status_code)
