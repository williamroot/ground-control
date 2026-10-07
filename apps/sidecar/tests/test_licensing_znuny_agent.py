"""T6 (teste V01) — licença só para agente que existe no Znuny.

No staging, 6 das 7 licenças em uso eram de logins que nunca existiram no
Znuny (`mariana`, `georgia`, ...): a rota aceitava qualquer texto digitado, e o
quadro de licenças contava seats de gente fictícia. Agora `PUT /agents`
confere o login contra `AdminAgentList` (a mesma integração de
`GET /v1/admin/znuny/agents`) antes de gravar.

Revogar continua aceitando login inexistente: é exatamente como se limpam as
licenças fantasmas que já estão gravadas.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.license_service import LicenseService
from gerti_sidecar.integrations import znuny_admin_people as people_gi
from gerti_sidecar.integrations.znuny_admin_people import Agent
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable
from gerti_sidecar.main import create_app

HOST = {"host": "gerti.was.dev.br"}

_AGENTS = [
    Agent(id=1, login="william", first_name="W", last_name="S", email="w@x", valid=True),
    Agent(id=2, login="georgia", first_name="Georgia", last_name="Lima", email="g@x", valid=True),
    Agent(id=3, login="antigo", first_name="A", last_name="B", email="a@x", valid=False),
]


def _wire(monkeypatch, engine, app_session_factory, *, agents=_AGENTS):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    calls: list[str] = []

    async def fake_list_agents(*, agent_login: str) -> list[Agent]:
        calls.append(agent_login)
        if agents is None:
            raise ZnunyUnavailable("down")
        return list(agents)

    monkeypatch.setattr(people_gi, "list_agents", fake_list_agents)
    return calls


async def _seats(session, n: int = 5) -> None:
    await LicenseService(session).set_seats_total(n, by="william")
    await session.commit()


def _client():
    c = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")
    c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))
    return c


@pytest.mark.asyncio
async def test_a_login_that_does_not_exist_in_znuny_is_422(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    await _seats(session)
    async with _client() as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "mariana", "modules": ["tickets"]},
        )
        assert r.status_code == 422
        assert r.json()["detail"] == (
            "O agente 'mariana' não existe no Znuny — cadastre-o antes de licenciar."
        )
        # Nada foi gravado: o seat continua livre.
        ov = await c.get("/v1/admin/licensing/overview", headers=HOST)
        assert ov.json()["seats_used"] == 0


@pytest.mark.asyncio
async def test_an_invalid_agent_in_znuny_is_422(engine, app_session_factory, session, monkeypatch):
    _wire(monkeypatch, engine, app_session_factory)
    await _seats(session)
    async with _client() as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "antigo", "modules": ["tickets"]},
        )
    assert r.status_code == 422
    assert "inativo no Znuny" in r.json()["detail"]


@pytest.mark.asyncio
async def test_an_existing_agent_is_licensed_with_the_znuny_login(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    await _seats(session)
    async with _client() as c:
        # Espaços e caixa diferentes resolvem para o login canônico do Znuny —
        # senão "Georgia" e "georgia" viravam dois seats para a mesma pessoa.
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "  Georgia ", "modules": ["tickets"]},
        )
    assert r.status_code == 200, r.text
    assert r.json()["agent_login"] == "georgia"
    assert r.json()["modules"] == ["tickets"]


@pytest.mark.asyncio
async def test_an_invented_module_is_422_listing_the_valid_ones_without_asking_znuny(
    engine, app_session_factory, session, monkeypatch
):
    calls = _wire(monkeypatch, engine, app_session_factory)
    await _seats(session)
    async with _client() as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "georgia", "modules": ["whatsapp"]},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "whatsapp" in detail
    assert "disponíveis: tickets, inventory" in detail
    assert calls == []


@pytest.mark.asyncio
async def test_znuny_down_is_503_and_nothing_is_written(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory, agents=None)
    await _seats(session)
    async with _client() as c:
        r = await c.put(
            "/v1/admin/licensing/agents",
            headers=HOST,
            json={"agent_login": "georgia", "modules": ["tickets"]},
        )
        assert r.status_code == 503
        assert r.json()["detail"] == "znuny_unavailable"
        ov = await c.get("/v1/admin/licensing/overview", headers=HOST)
        assert ov.json()["seats_used"] == 0


@pytest.mark.asyncio
async def test_revoking_a_ghost_licence_does_not_ask_znuny(
    engine, app_session_factory, session, monkeypatch
):
    """A licença fantasma (gravada antes desta guarda) tem de poder sair."""
    calls = _wire(monkeypatch, engine, app_session_factory, agents=None)
    await _seats(session)
    await LicenseService(session).assign("mariana", ["tickets"], by="william")
    await session.commit()
    async with _client() as c:
        r = await c.delete("/v1/admin/licensing/agents/mariana", headers=HOST)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    assert calls == []
