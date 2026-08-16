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
    """Captura as chamadas GI monkeypatched.

    Onda 1 acrescentou três operações (`CustomerCompanyUpdate`,
    `CustomerUserUpdate`, `CustomerUserList`). O spy passa a cobri-las e a
    manter um "Znuny de mentira" em memória (`self.directory`), para que
    `list_customer_users` reflita o que foi criado/alterado — sem isso, a
    listagem por Znuny não teria como ser exercitada.
    """

    def __init__(self) -> None:
        self.companies: list[tuple[str, str]] = []
        self.users: list[dict[str, str]] = []
        self.passwords: list[tuple[str, str]] = []
        self.company_updates: list[dict[str, object]] = []
        self.user_updates: list[dict[str, object]] = []
        # login -> registro, no formato que o Znuny devolveria
        self.directory: dict[str, gi.ZnunyCustomerUser] = {}
        self._owner: dict[str, str] = {}  # login -> CustomerID dono

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _company(customer_id, company_name, *, valid=True):
            self.companies.append((customer_id, company_name))
            return customer_id

        async def _user(
            *,
            login,
            email,
            first_name,
            last_name,
            customer_id,
            valid=True,
            phone=None,
            mobile=None,
        ):
            self.users.append(
                {
                    "login": login,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "customer_id": customer_id,
                    "phone": phone or "",
                    "mobile": mobile or "",
                }
            )
            self.directory[login.lower()] = gi.ZnunyCustomerUser(
                login=login,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone or "",
                mobile=mobile or "",
                active=valid,
            )
            self._owner[login.lower()] = customer_id
            return login

        async def _password(login, password):
            self.passwords.append((login, password))

        async def _company_update(customer_id, **kwargs):
            self.company_updates.append({"customer_id": customer_id, **kwargs})
            return customer_id

        async def _user_update(login, **kwargs):
            self.user_updates.append({"login": login, **kwargs})
            cur = self.directory.get(login.lower())
            if cur is not None:
                self.directory[login.lower()] = gi.ZnunyCustomerUser(
                    login=cur.login,
                    first_name=kwargs.get("first_name") or cur.first_name,
                    last_name=kwargs.get("last_name") or cur.last_name,
                    email=kwargs.get("email") or cur.email,
                    phone=cur.phone if kwargs.get("phone") is None else kwargs["phone"],
                    mobile=cur.mobile if kwargs.get("mobile") is None else kwargs["mobile"],
                    active=cur.active if kwargs.get("valid") is None else bool(kwargs["valid"]),
                )

        async def _user_list(customer_id):
            return gi.CustomerUserPage(
                users=[
                    u
                    for login, u in sorted(self.directory.items())
                    if self._owner.get(login) == customer_id
                ],
                truncated=False,
            )

        monkeypatch.setattr(gi, "create_customer_company", _company)
        monkeypatch.setattr(gi, "create_customer_user", _user)
        monkeypatch.setattr(gi, "set_password", _password)
        monkeypatch.setattr(gi, "update_customer_company", _company_update)
        monkeypatch.setattr(gi, "update_customer_user", _user_update)
        monkeypatch.setattr(gi, "list_customer_users", _user_list)


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
    spy = _GISpy()
    spy.install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        r1 = await c.post(
            "/v1/admin/tenants",
            headers=_HOST,
            json=_onboard_body(customer="ACME", subdomain="acme"),
        )
        assert r1.status_code == 201
        gi_after_first = (len(spy.companies), len(spy.users), len(spy.passwords))
        # MESMO subdomínio, cliente DIFERENTE → conflito limpo (4xx, não 500).
        r2 = await c.post(
            "/v1/admin/tenants",
            headers=_HOST,
            json=_onboard_body(customer="OTHER", subdomain="acme"),
        )
    assert r2.status_code == 409, r2.text
    assert "acme" in r2.json()["detail"]
    # Conflito resolvido no Postgres ANTES de qualquer escrita no Znuny: o
    # cliente OTHER rejeitado NÃO criou CustomerCompany/User/senha (zero órfãos).
    assert (len(spy.companies), len(spy.users), len(spy.passwords)) == gi_after_first
    assert all(co != "OTHER" for co, _ in spy.companies)


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
            ("PUT", "/v1/admin/tenants/abc"),
            ("POST", "/v1/admin/tenants/abc/users"),
            ("GET", "/v1/admin/tenants/abc/users"),
            ("PUT", "/v1/admin/tenants/abc/users/ana@acme.example"),
            ("GET", "/v1/admin/tenants/abc/queues"),
            ("PUT", "/v1/admin/tenants/abc/queues"),
        ]:
            r = await c.request(method, path, headers=_HOST, json={})
            assert r.status_code == 401, (method, path, r.status_code)


# ── T-R1.2 / Onda 1 — editar o cadastro depois de criado ────────────────────


async def _onboarded(c, settings) -> str:
    c.cookies.set("gsid_adm", _admin_cookie(settings))
    r = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
    assert r.status_code == 201, r.text
    return str(r.json()["tenant"]["id"])


@pytest.mark.asyncio
async def test_update_tenant_persists_registration(engine, session, monkeypatch):
    """V-R1.1 / aceite A1.1 — corrigir razão social e endereço, e a correção fica."""
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    spy = _GISpy()
    spy.install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        tid = await _onboarded(c, settings)
        r = await c.put(
            f"/v1/admin/tenants/{tid}",
            headers=_HOST,
            json={
                "legal_name": "Nova Razão LTDA",
                "address_city": "Belo Horizonte",
                "address_state": "MG",
                "address_zip": "30110000",
                "contact_name": "Ana Contato",
            },
        )
        assert r.status_code == 200, r.text
        again = await c.get(f"/v1/admin/tenants/{tid}", headers=_HOST)

    body = again.json()
    assert body["legal_name"] == "Nova Razão LTDA"
    assert body["address_city"] == "Belo Horizonte"
    assert body["contact_name"] == "Ana Contato"
    # A1.4 — o endereço também foi espelhado no Znuny.
    assert spy.company_updates, "CustomerCompanyUpdate não foi chamado"
    mirror = spy.company_updates[-1]
    assert mirror["customer_id"] == "ACME"
    assert mirror["city"] == "Belo Horizonte/MG"
    assert "Ana Contato" in str(mirror["comment"])


@pytest.mark.asyncio
async def test_update_tenant_rejects_immutable_subdomain(engine, session, monkeypatch):
    """V-R1.2 / aceite A1.2 — subdomínio é imutável, e o valor no banco não muda."""
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        tid = await _onboarded(c, settings)
        r = await c.put(f"/v1/admin/tenants/{tid}", headers=_HOST, json={"subdomain": "outro"})
        assert r.status_code == 422, r.text
        r2 = await c.put(
            f"/v1/admin/tenants/{tid}", headers=_HOST, json={"znuny_customer_id": "OUTRO"}
        )
        assert r2.status_code == 422, r2.text

    tenant = (
        await session.execute(select(Tenant).where(Tenant.znuny_customer_id == "ACME"))
    ).scalar_one()
    assert tenant.subdomain == "acme"
    assert tenant.znuny_customer_id == "ACME"


@pytest.mark.asyncio
async def test_update_tenant_unknown_id_is_404(engine, session, monkeypatch):
    """V-R1.3 — id inexistente devolve 404, nunca 403 nem 500."""
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        ghost = "11111111-2222-3333-4444-555555555555"
        r = await c.put(f"/v1/admin/tenants/{ghost}", headers=_HOST, json={"trade_name": "X"})
        assert r.status_code == 404, r.text
        r2 = await c.put("/v1/admin/tenants/nao-e-uuid", headers=_HOST, json={"trade_name": "X"})
        assert r2.status_code == 404, r2.text


@pytest.mark.asyncio
async def test_update_tenant_audits_before_and_after(engine, session, monkeypatch):
    """A trilha precisa dizer o que era, não só que mudou."""
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        tid = await _onboarded(c, settings)
        r = await c.put(f"/v1/admin/tenants/{tid}", headers=_HOST, json={"legal_name": "Depois SA"})
        assert r.status_code == 200, r.text

    from gerti_sidecar.models import AuditLog

    row = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.entity == "tenant", AuditLog.action == "update")
                .order_by(AuditLog.at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.metadata_json["legal_name"] == {
        "antes": "Acme Indústria Ltda.",
        "depois": "Depois SA",
    }


@pytest.mark.asyncio
async def test_update_tenant_noop_does_not_touch_znuny(engine, session, monkeypatch):
    """Mandar o valor que já está lá não vira escrita no Znuny nem linha de auditoria."""
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    spy = _GISpy()
    spy.install(monkeypatch)

    app = create_app()
    async with _client(app) as c:
        tid = await _onboarded(c, settings)
        r = await c.put(f"/v1/admin/tenants/{tid}", headers=_HOST, json={"trade_name": "Acme"})
        assert r.status_code == 200, r.text
    assert spy.company_updates == []


@pytest.mark.asyncio
async def test_onboarding_accepts_address_and_contact(engine, session, monkeypatch):
    """A etapa 1 do assistente manda endereço e contato — eles não podem sumir.

    Sem este teste, `NewTenantBody` ignoraria os campos em silêncio (Pydantic
    descarta chave desconhecida por padrão) e o operador acharia que cadastrou
    o endereço quando não cadastrou.
    """
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    _GISpy().install(monkeypatch)

    body = _onboard_body()
    body |= {
        "address_street": "Rua das Acácias",
        "address_number": "100",
        "address_district": "Centro",
        "address_city": "Belo Horizonte",
        "address_state": "MG",
        "address_zip": "30110000",
        "contact_name": "Ana Contato",
        "contact_email": "ana@acme.example",
        "contact_phone": "+553133330000",
    }
    body["users"][0] |= {"phone": "+553133331111", "extension": "204"}

    app = create_app()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", _admin_cookie(settings))
        r = await c.post("/v1/admin/tenants", headers=_HOST, json=body)
    assert r.status_code == 201, r.text
    detail = r.json()["tenant"]
    assert detail["address_city"] == "Belo Horizonte"
    assert detail["contact_email"] == "ana@acme.example"

    tenant = (
        await session.execute(select(Tenant).where(Tenant.znuny_customer_id == "ACME"))
    ).scalar_one()
    assert tenant.address_street == "Rua das Acácias"
    assert tenant.address_zip == "30110000"

    role = (
        await session.execute(
            select(PortalUserRole).where(
                func.lower(PortalUserRole.customer_login) == "admin@acme.example"
            )
        )
    ).scalar_one()
    assert role.extension == "204"
    assert role.email_intake_enabled is True
