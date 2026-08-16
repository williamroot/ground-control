"""/v1/admin/tenants/{id}/users — cadastro único da pessoa do cliente (R2, Onda 1).

R2 é o requisito mais importante do vídeo, e não é paridade com o TIFLUX: é a
correção do defeito que o Kleber diz ter reclamado várias vezes sem ser
atendido — duas fichas para a mesma pessoa, uma "do portal" e outra "de
e-mail", com os chamados de e-mail nunca aparecendo no portal dela.

O que estes testes provam:
  • V-R2.1  telefone, celular, ramal e as chaves entram e voltam no cadastro
  • V-R2.2  usuário criado direto no Znuny APARECE no console (A2.5) — o caso
            que hoje some
  • A2.4    desativar é ValidID=2 no Znuny, e a pessoa continua existindo
  • V-R2.5  toda rota exige sessão de agente; usuário de outra empresa dá 404

O Znuny é falso (o `_GISpy` de `test_admin_tenants`, que mantém um diretório em
memória), mas o contrato exercitado é o real: as mesmas funções que o router
chama em produção.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.main import create_app
from gerti_sidecar.models import PortalUserRole, ZnunyInstance
from gerti_sidecar.models.enums import PortalRole
from tests.test_admin_tenants import _GISpy, _onboard_body

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


def _wire_admin_db(monkeypatch: pytest.MonkeyPatch, engine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)


async def _seed_instance(session: AsyncSession) -> None:
    session.add(
        ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
    )
    await session.commit()


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, session, monkeypatch) -> tuple[object, _GISpy, str]:
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    _wire_admin_db(monkeypatch, engine)
    spy = _GISpy()
    spy.install(monkeypatch)
    return settings, spy, create_app()


@pytest.mark.asyncio
async def test_create_user_with_phone_and_extension(engine, session, monkeypatch):
    """V-R2.1 — telefone/celular vão ao Znuny; ramal e a chave de e-mail ficam aqui."""
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        r = await c.post(
            f"/v1/admin/tenants/{tid}/users",
            headers=_HOST,
            json={
                "email": "ana@acme.example",
                "first_name": "Ana",
                "last_name": "Souza",
                "password": "pw-forte",
                "role": "helpdesk",
                "phone": "+553133330000",
                "mobile": "+5531999990000",
                "extension": "204",
                "email_intake_enabled": True,
            },
        )
        assert r.status_code == 201, r.text

        listed = await c.get(f"/v1/admin/tenants/{tid}/users", headers=_HOST)

    assert listed.status_code == 200, listed.text
    users = {u["customer_login"]: u for u in listed.json()["users"]}
    ana = users["ana@acme.example"]
    assert ana["phone"] == "+553133330000"
    assert ana["mobile"] == "+5531999990000"
    assert ana["extension"] == "204"
    assert ana["role"] == "helpdesk"
    assert ana["email_intake_enabled"] is True
    assert ana["has_portal_access"] is True
    # A senha foi para a operação separada, nunca junto do cadastro.
    assert ("ana@acme.example", "pw-forte") in spy.passwords
    assert all("password" not in u for u in spy.user_updates)


@pytest.mark.asyncio
async def test_user_created_straight_in_znuny_shows_up(engine, session, monkeypatch):
    """V-R2.2 / aceite A2.5 — quem nasceu no painel do Znuny deixa de ser invisível.

    Este é o defeito concreto: a ficha listava `portal_user_role`, a NOSSA
    tabela. Uma pessoa criada direto no Znuny — ou, a partir do R9, auto-criada
    pelo PostMaster ao mandar o primeiro e-mail — não existia para o console.
    """
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        # Alguém aparece no Znuny sem passar pelo console e sem papel nenhum.
        spy.directory["externo@acme.example"] = gi.ZnunyCustomerUser(
            login="externo@acme.example",
            first_name="Externo",
            last_name="Dozunuy",
            email="externo@acme.example",
            phone="",
            mobile="",
            active=True,
        )
        spy._owner["externo@acme.example"] = "ACME"

        listed = await c.get(f"/v1/admin/tenants/{tid}/users", headers=_HOST)

    users = {u["customer_login"]: u for u in listed.json()["users"]}
    assert "externo@acme.example" in users
    externo = users["externo@acme.example"]
    assert externo["has_portal_access"] is False
    assert externo["role"] is None
    assert listed.json()["degraded"] is False


@pytest.mark.asyncio
async def test_deactivate_user_is_valid_id_two_not_delete(engine, session, monkeypatch):
    """Aceite A2.4 — desativar preserva a pessoa (invariante 3: sem exclusão)."""
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        r = await c.put(
            f"/v1/admin/tenants/{tid}/users/help@acme.example",
            headers=_HOST,
            json={"active": False},
        )
        assert r.status_code == 200, r.text
        assert r.json()["active"] is False

        listed = await c.get(f"/v1/admin/tenants/{tid}/users", headers=_HOST)

    # Continua na lista, marcada como inativa — não sumiu.
    users = {u["customer_login"]: u for u in listed.json()["users"]}
    assert users["help@acme.example"]["active"] is False
    assert any(u.get("valid") is False for u in spy.user_updates)


@pytest.mark.asyncio
async def test_update_user_can_flip_email_intake_and_role(engine, session, monkeypatch):
    """A chave "libera chamados por e-mail" (01:44) e o papel são editáveis."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        r = await c.put(
            f"/v1/admin/tenants/{tid}/users/help@acme.example",
            headers=_HOST,
            json={"email_intake_enabled": False, "role": "admin", "extension": "310"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["email_intake_enabled"] is False
        assert r.json()["role"] == "admin"
        assert r.json()["extension"] == "310"

    row = (
        await session.execute(
            select(PortalUserRole).where(
                func.lower(PortalUserRole.customer_login) == "help@acme.example"
            )
        )
    ).scalar_one()
    assert row.email_intake_enabled is False
    assert row.role == PortalRole.admin
    assert row.extension == "310"


@pytest.mark.asyncio
async def test_update_user_of_another_tenant_is_404(engine, session, monkeypatch):
    """V-R2.5 (anti-IDOR) — pessoa de OUTRA empresa não é editável por este tenant."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        a = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]
        b_body = _onboard_body(customer="BETA", subdomain="beta")
        b_body["users"] = [
            {
                "email": "bruno@beta.example",
                "first_name": "Bruno",
                "last_name": "Beta",
                "password": "pw",
                "role": "admin",
            }
        ]
        await c.post("/v1/admin/tenants", headers=_HOST, json=b_body)

        # Tenant A tentando mexer no usuário do tenant B.
        r = await c.put(
            f"/v1/admin/tenants/{a}/users/bruno@beta.example",
            headers=_HOST,
            json={"active": False},
        )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_user_routes_reject_customer_cookie(engine, session, monkeypatch):
    """V-R2.5 — cookie de CLIENTE (`gsid`) não abre rota de console."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

    async with _client(app) as c2:
        c2.cookies.set("gsid", "cookie-de-cliente-nao-serve")
        for method, path in [
            ("GET", f"/v1/admin/tenants/{tid}/users"),
            ("POST", f"/v1/admin/tenants/{tid}/users"),
            ("PUT", f"/v1/admin/tenants/{tid}/users/help@acme.example"),
        ]:
            r = await c2.request(method, path, headers=_HOST, json={})
            assert r.status_code == 401, (method, path, r.status_code)


@pytest.mark.asyncio
async def test_list_users_degrades_when_znuny_is_down(engine, session, monkeypatch):
    """Znuny fora não pode transformar a lista em vazio silencioso.

    Uma tela que mostra "nenhum usuário" quando o Znuny caiu é indistinguível
    de uma tela que mostra que alguém apagou todo mundo. `degraded` existe para
    a tela poder dizer a diferença.
    """
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        async def _down(customer_id):
            raise gi.ZnunyUnavailable("timeout")

        monkeypatch.setattr(gi, "list_customer_users", _down)
        r = await c.get(f"/v1/admin/tenants/{tid}/users", headers=_HOST)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["degraded"] is True
    assert body["truncated"] is False
    # Os dois do onboarding continuam visíveis, vindos da nossa tabela.
    assert len(body["users"]) == 2


@pytest.mark.asyncio
async def test_truncated_listing_is_flagged(engine, session, monkeypatch):
    """Lista cortada pelo teto do Znuny não pode passar por lista completa.

    A op Perl tem teto de 500 pessoas e diz quando bateu nele. Se o console
    engolisse essa marca, o operador leria "faltou gente" como exclusão.
    """
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tid = (await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())).json()[
            "tenant"
        ]["id"]

        async def _cut(customer_id):
            return gi.CustomerUserPage(users=[], truncated=True)

        monkeypatch.setattr(gi, "list_customer_users", _cut)
        r = await c.get(f"/v1/admin/tenants/{tid}/users", headers=_HOST)

    assert r.status_code == 200, r.text
    assert r.json()["truncated"] is True
