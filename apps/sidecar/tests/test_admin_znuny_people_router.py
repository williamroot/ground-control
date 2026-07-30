"""`/v1/admin/znuny/{agents,groups,calendar}` — router (Spec #4, Blocos C e D).

Cobre exatamente as guardas exigidas pelo contrato:
  • 401 sem `gsid_adm`.
  • NENHUMA senha/hash vaza na resposta de agente (mesmo que o mock do GI
    "esqueça" de filtrar — defesa em profundidade do sidecar, ponta a ponta).
  • 422 de forma inválida de jornada e de feriado, SEM tocar no Znuny.
  • 404 de setting fora da allowlist e de id de agente malformado.
  • Mudança de permissão audita o antes E o depois (não só "atualizou").
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models.audit_log import AuditLog

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ZNUNY_ADMIN_WS_URL", "http://znuny/Webservice/GertiAdmin")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "top-secret-admin-token")
    get_settings.cache_clear()
    return get_settings()


def _wire(monkeypatch, engine, app_session_factory) -> async_sessionmaker[AsyncSession]:
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    return admin_factory


class _MockResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _mock_post(payload, status_code: int = 200):
    async def post(self, url, **kw):
        return _MockResp(status_code, payload)

    return post


def _forbid_znuny_call(monkeypatch):
    """Faz o teste falhar se o código tentar tocar no Znuny (guarda `sem tocar`)."""

    async def boom(self, url, **kw):
        raise AssertionError(f"não deveria chamar o Znuny: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)


@pytest.mark.asyncio
async def test_list_agents_requires_admin_session(engine, app_session_factory, monkeypatch):
    _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/admin/znuny/agents", headers=_HOST)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_agents_never_leaks_password_in_response(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_post(
            {
                "Agents": [
                    {
                        "UserID": 3,
                        "UserLogin": "joe",
                        "UserFirstname": "Joe",
                        "UserLastname": "Doe",
                        "UserEmail": "joe@gerti.com",
                        # Simula um GI que "esqueceu" de filtrar — o sidecar
                        # TEM que filtrar de qualquer forma.
                        "UserPw": "$2y$10$superSecretHashValueXYZ",
                        "ValidID": 1,
                    }
                ]
            }
        ),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/agents", headers=_HOST)

    assert r.status_code == 200
    raw = r.text
    assert "UserPw" not in raw
    assert "superSecretHashValueXYZ" not in raw
    assert "top-secret-admin-token" not in raw
    body = r.json()
    for agent in body:
        for key in agent:
            assert "pw" not in key.lower()
            assert "password" not in key.lower()


@pytest.mark.asyncio
async def test_get_agent_malformed_id_is_404(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)  # guarda numérica é ANTES de qualquer chamada ao GI
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/agents/not-a-number", headers=_HOST)
    assert r.status_code == 404
    assert r.json()["detail"] == "agent_not_found"


@pytest.mark.asyncio
async def test_calendar_get_unknown_setting_is_404(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendar", params={"setting": "TicketHook"}, headers=_HOST)
    assert r.status_code == 404
    assert r.json()["detail"] == "setting_not_found"


@pytest.mark.asyncio
async def test_calendar_put_unknown_setting_is_404(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/calendar",
            json={"setting": "TicketHook", "value": "whatever"},
            headers=_HOST,
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "setting_not_found"


@pytest.mark.asyncio
async def test_calendar_put_invalid_jornada_shape_is_422(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)  # forma errada -> 422 SEM tocar no Znuny
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/calendar",
            json={"setting": "TimeWorkingHours", "value": {"Mon": [25]}},  # hora inválida
            headers=_HOST,
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_calendar_put_invalid_feriado_shape_is_422(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/calendar",
            json={"setting": "TimeVacationDays", "value": {"13": {"1": "mês inválido"}}},
            headers=_HOST,
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_agent_groups_put_audits_before_and_after(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_post(
            {
                "UserID": 7,
                "Before": [{"GroupID": 1, "Name": "users"}],
                "After": [
                    {"GroupID": 1, "Name": "users"},
                    {"GroupID": 2, "Name": "admin"},
                ],
            }
        ),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/agents/7/groups",
            json={"group_ids": [1, 2]},
            headers=_HOST,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"] == [{"id": 1, "name": "users"}]
    assert body["after"] == [{"id": 1, "name": "users"}, {"id": 2, "name": "admin"}]

    async with admin_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "znuny_agent_groups", AuditLog.entity_id == "7"
                )
            )
        ).scalar_one()
        assert row.actor_login == "william"
        assert row.actor_type == "agent"
        assert row.action == "update"
        # a auditoria registra os DOIS estados, não só "atualizou".
        assert row.metadata_json["before"] == [{"id": 1, "name": "users"}]
        assert row.metadata_json["after"] == [
            {"id": 1, "name": "users"},
            {"id": 2, "name": "admin"},
        ]


@pytest.mark.asyncio
async def test_agent_groups_put_anti_lockout_maps_to_422(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_post({"Error": {"ErrorMessage": "you cannot remove yourself from the admin group."}}),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/agents/7/groups",
            json={"group_ids": []},
            headers=_HOST,
        )
    assert r.status_code == 422
    assert "admin group" in r.json()["detail"]
