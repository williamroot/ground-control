"""A16.3 — o caso da Georgia, **pela URL direta**.

*"A Georgia só usa tickets e não tem acesso remoto, então ela não vê o
inventário"* (10:00).

O termo de aceite é explícito: *"nem pela URL direta"*. Esconder o item no
menu não é controle de acesso — é decoração. Estes testes batem na rota HTTP,
que é o único lugar onde a afirmação pode ser provada.

A onda anterior ensinou por que isso importa: um teste de serviço verde não
prova rota. Lá a guarda de fila era código morto porque o campo nunca chegava
ao serviço; aqui o risco simétrico seria o gate existir e não estar pendurado
em nenhuma rota.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.license_service import LicenseService
from gerti_sidecar.models import Tenant, ZnunyInstance

HOST = {"host": "gerti.was.dev.br"}


async def _seed(session) -> Tenant:
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
        legal_name="Acme",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.commit()
    return t


def _wire(monkeypatch, engine, app_session_factory, *, enforce: bool):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LICENSE_ENFORCEMENT_ENABLED", "true" if enforce else "false")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


async def _licence(session, login: str, modules: list[str], *, seats: int = 5):
    svc = LicenseService(session)
    await svc.set_seats_total(seats, by="william")
    await svc.assign(login, modules, by="william")
    await session.commit()


def _client(app, login: str):
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    c.cookies.set("gsid_adm", encode_admin_session(login, get_settings()))
    return c


@pytest.mark.asyncio
async def test_georgia_cannot_reach_the_inventory_url(
    engine, app_session_factory, session, monkeypatch
):
    """O aceite inteiro numa linha: 403 na rota, com a URL digitada à mão."""
    _wire(monkeypatch, engine, app_session_factory, enforce=True)
    t = await _seed(session)
    await _licence(session, "georgia", ["tickets"])

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "georgia") as c:
        r = await c.get(f"/v1/admin/tenants/{t.id}/devices", headers=HOST)
    assert r.status_code == 403
    # A mensagem diz QUAL módulo falta — um 403 mudo faria a agente abrir
    # chamado achando que o sistema quebrou.
    assert "inventory" in r.json()["detail"]


@pytest.mark.asyncio
async def test_an_agent_with_the_module_gets_through(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory, enforce=True)
    t = await _seed(session)
    await _licence(session, "william", ["tickets", "inventory"])

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "william") as c:
        r = await c.get(f"/v1/admin/tenants/{t.id}/devices", headers=HOST)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_an_agent_with_no_licence_at_all_is_blocked_when_enforcing(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory, enforce=True)
    t = await _seed(session)

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "desconhecido") as c:
        r = await c.get(f"/v1/admin/tenants/{t.id}/devices", headers=HOST)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_with_enforcement_off_nothing_changes(
    engine, app_session_factory, session, monkeypatch
):
    """O padrão. Ligar o gate sem licenças atribuídas trancaria TODOS para fora.

    A Gerti atribui as licenças, confere o quadro, e só então liga a chave.
    """
    _wire(monkeypatch, engine, app_session_factory, enforce=False)
    t = await _seed(session)

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "georgia") as c:
        r = await c.get(f"/v1/admin/tenants/{t.id}/devices", headers=HOST)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_the_write_routes_are_gated_too(engine, app_session_factory, session, monkeypatch):
    """Gatear só a leitura deixaria a agente aprovar um dispositivo que não vê."""
    _wire(monkeypatch, engine, app_session_factory, enforce=True)
    t = await _seed(session)
    await _licence(session, "georgia", ["tickets"])

    from gerti_sidecar.main import create_app

    dev = "11111111-1111-1111-1111-111111111111"
    async with _client(create_app(), "georgia") as c:
        approve = await c.post(f"/v1/admin/tenants/{t.id}/devices/{dev}/approve", headers=HOST)
        revoke = await c.post(f"/v1/admin/tenants/{t.id}/devices/{dev}/revoke", headers=HOST)
    assert approve.status_code == 403
    assert revoke.status_code == 403


@pytest.mark.asyncio
async def test_licensing_data_never_reaches_a_client_route(
    engine, app_session_factory, session, monkeypatch
):
    """A16.5 — nenhuma rota de cliente expõe licenciamento.

    A checagem é sobre o CONJUNTO de rotas do app: qualquer caminho de
    licenciamento tem de estar sob `/v1/admin/`. Assim, expor licença numa
    rota de cliente no futuro quebra este teste em vez de vazar em silêncio.
    """
    _wire(monkeypatch, engine, app_session_factory, enforce=True)

    from gerti_sidecar.main import create_app

    paths = [getattr(r, "path", "") for r in create_app().routes]
    leaked = [
        p for p in paths if ("licens" in p or "seats" in p) and not p.startswith("/v1/admin/")
    ]
    assert leaked == [], f"licenciamento exposto fora do console: {leaked}"


@pytest.mark.asyncio
async def test_the_overview_route_reports_whether_the_gate_is_on(
    engine, app_session_factory, session, monkeypatch
):
    """Quadro que promete controle sem controlar é pior do que nenhum quadro."""
    _wire(monkeypatch, engine, app_session_factory, enforce=False)
    await _seed(session)
    await _licence(session, "william", ["tickets"])

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "william") as c:
        r = await c.get("/v1/admin/licensing/overview", headers=HOST)
    assert r.status_code == 200
    body = r.json()
    assert body["enforcement_enabled"] is False
    assert body["seats_used"] == 1


@pytest.mark.asyncio
async def test_assigning_over_the_cap_is_422_at_the_route(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory, enforce=False)
    await _seed(session)
    await _licence(session, "william", ["tickets"], seats=1)

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "william") as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "georgia", "modules": ["tickets"]},
        )
    assert r.status_code == 422
    assert "1 de 1" in r.json()["detail"]


@pytest.mark.asyncio
async def test_an_invented_module_is_422_at_the_route(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory, enforce=False)
    await _seed(session)
    await _licence(session, "william", ["tickets"])

    from gerti_sidecar.main import create_app

    async with _client(create_app(), "william") as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "georgia", "modules": ["whatsapp"]},
        )
    assert r.status_code == 422
    assert "whatsapp" in r.json()["detail"]
