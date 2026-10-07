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


_ORIGINAL_ASYNC_CLIENT_POST = httpx.AsyncClient.post


def _is_znuny_url(url: object) -> bool:
    # Checa o HOST, não uma substring solta: o path do próprio sidecar sob
    # teste também contém "znuny" (`/v1/admin/znuny/...`), então uma checagem
    # ingênua de substring casaria com a chamada do client de teste também.
    return str(url).startswith("http://znuny/")


def _mock_znuny_post(payload, status_code: int = 200):
    """Como `_mock_post`, mas só intercepta chamadas ao Znuny (host `znuny`).
    Necessário para rotas do PRÓPRIO sidecar que são POST (ex.:
    `/agents/{id}/password`): como `httpx.AsyncClient.post` é um método de
    classe, um mock ingênuo intercepta as DUAS chamadas — inclusive a do
    client de teste (ASGITransport) para o endpoint sob teste. Chamadas que
    não são para o Znuny passam pelo `.post` real."""

    async def post(self, url, **kw):
        if not _is_znuny_url(url):
            return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
        return _MockResp(status_code, payload)

    return post


def _forbid_znuny_gi_call(monkeypatch):
    """Como `_forbid_znuny_call`, mas só barra chamadas ao Znuny — mesma razão
    de `_mock_znuny_post` acima (o endpoint sob teste também é POST)."""

    async def guard(self, url, **kw):
        if _is_znuny_url(url):
            raise AssertionError(f"não deveria chamar o Znuny: {url}")
        return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "post", guard)


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


# --------------------------------------------------------------------------- #
# POST /agents/{id}/password — operação SEPARADA (correção pós-revisão
# adversarial): NUNCA um efeito colateral de PUT /agents/{id}.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_set_agent_password_requires_admin_session(engine, app_session_factory, monkeypatch):
    _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_gi_call(monkeypatch)  # dependência de auth roda ANTES de qualquer chamada ao GI
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/znuny/agents/7/password",
            json={"new_password": "senha-super-segura"},
            headers=_HOST,
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_set_agent_password_malformed_id_is_404(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_gi_call(monkeypatch)  # guarda numérica é ANTES de qualquer chamada ao GI
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            "/v1/admin/znuny/agents/not-a-number/password",
            json={"new_password": "senha-super-segura"},
            headers=_HOST,
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "agent_not_found"


@pytest.mark.asyncio
async def test_set_agent_password_too_short_is_422_without_writing(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_gi_call(monkeypatch)  # Pydantic 422 -> nunca toca no Znuny
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            "/v1/admin/znuny/agents/7/password",
            json={"new_password": "curta"},
            headers=_HOST,
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_set_agent_password_happy_never_leaks_and_audits_fact_only(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)

    captured: dict = {}

    async def post(self, url, **kw):
        if not _is_znuny_url(url):
            return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResp(200, {"Success": 1, "UserID": 7, "UserLogin": "joe"})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            "/v1/admin/znuny/agents/7/password",
            json={"new_password": "senha-super-segura"},
            headers=_HOST,
        )

    assert r.status_code == 204
    assert r.text == ""
    assert "senha-super-segura" not in r.text

    # o corpo mandado ao Znuny leva a senha (é a escrita real) — mas a
    # RESPOSTA HTTP ao console e a auditoria abaixo, não.
    assert captured["json"]["NewPassword"] == "senha-super-segura"
    assert captured["json"]["TargetUserID"] == 7
    assert captured["json"]["AgentLogin"] == "william"

    async with admin_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "znuny_agent_password", AuditLog.entity_id == "7"
                )
            )
        ).scalar_one()
        assert row.actor_login == "william"
        assert row.action == "update"
        assert "senha-super-segura" not in row.description
        # SÓ o fato é auditado — nenhum metadata (a coluna tem default '{}',
        # não NULL, mas o ponto é: nada de conteúdo, muito menos a senha).
        assert not row.metadata_json


@pytest.mark.asyncio
async def test_set_agent_password_znuny_rejection_maps_to_422_without_leaking(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_znuny_post({"Error": {"ErrorMessage": "agent not found"}}),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            "/v1/admin/znuny/agents/999/password",
            json={"new_password": "senha-super-segura"},
            headers=_HOST,
        )
    assert r.status_code == 422
    assert "senha-super-segura" not in r.text


class _FakeSysConfig:
    """Znuny de mentira com ESTADO: `Get` lê do estado, `Set` grava nele e
    registra o nome gravado. Necessário desde que o PUT do calendário passou a
    ler o estado atual e gravar só o que mudou (teste V01)."""

    def __init__(self, state: dict | None = None, fail_on: dict | None = None):
        self.state: dict = dict(state or {})
        self.sets: list[str] = []
        self.fail_on: dict = dict(fail_on or {})

    def install(self, monkeypatch):
        fake = self

        async def post(self, url, **kw):
            if not _is_znuny_url(url):
                return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
            body = kw.get("json") or {}
            if str(url).endswith("/SysConfig/Get"):
                names = body.get("Names") or [body.get("Name")]
                return _MockResp(
                    200,
                    {
                        "Settings": {
                            n: {"Name": n, "EffectiveValue": fake.state.get(n, "")} for n in names
                        }
                    },
                )
            name = body.get("Name")
            fake.sets.append(name)
            if name in fake.fail_on:
                return _MockResp(200, fake.fail_on[name])
            fake.state[name] = body.get("EffectiveValue")
            return _MockResp(
                200, {"Name": name, "EffectiveValue": body.get("EffectiveValue"), "Deployed": 1}
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", post)
        return self


def _valid_calendar_body(calendar: str = "") -> dict:
    return {
        "calendar": calendar,
        "time_working_hours": {"Mon": [8, 9, 10]},
        "time_vacation_days": {"1": {"1": "Confraternização"}},
        "time_vacation_days_one_time": {"2026": {"12": {"25": "Natal 2026"}}},
        # T-R13.2 — `None` = "não mexer no nome". O corpo de escrita padrão
        # não mexe: só quem quer renomear manda o campo.
        "name": None,
    }


@pytest.mark.asyncio
async def test_calendar_get_unknown_calendar_suffix_is_404(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendar", params={"calendar": "10"}, headers=_HOST)
    assert r.status_code == 404
    assert r.json()["detail"] == "calendar_not_found"


@pytest.mark.asyncio
async def test_calendar_put_unknown_calendar_suffix_is_404(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put(
            "/v1/admin/znuny/calendar",
            json=_valid_calendar_body("abc"),
            headers=_HOST,
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "calendar_not_found"


@pytest.mark.asyncio
async def test_calendar_put_invalid_jornada_shape_is_422_without_writing(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)  # forma errada -> 422 SEM tocar no Znuny
    transport = ASGITransport(app=create_app())
    body = _valid_calendar_body()
    body["time_working_hours"] = {"Mon": [25]}  # hora inválida
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_calendar_put_invalid_feriado_shape_is_422_without_writing(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    body = _valid_calendar_body()
    body["time_vacation_days"] = {"13": {"1": "mês inválido"}}
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_calendar_put_invalid_feriado_pontual_shape_is_422_without_writing(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    _forbid_znuny_call(monkeypatch)
    transport = ASGITransport(app=create_app())
    body = _valid_calendar_body()
    body["time_vacation_days_one_time"] = {"26": {"12": {"25": "ano com 2 dígitos"}}}
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_calendar_get_composed_happy_path(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_post(
            {
                "Settings": {
                    "TimeWorkingHours::Calendar3": {
                        "Name": "TimeWorkingHours::Calendar3",
                        "EffectiveValue": {"Mon": [8, 9]},
                    },
                    "TimeVacationDays::Calendar3": {
                        "Name": "TimeVacationDays::Calendar3",
                        "EffectiveValue": {"1": {"1": "Confraternização"}},
                    },
                    "TimeVacationDaysOneTime::Calendar3": {
                        "Name": "TimeVacationDaysOneTime::Calendar3",
                        "EffectiveValue": {"2026": {"12": {"25": "Natal 2026"}}},
                    },
                }
            }
        ),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendar", params={"calendar": "3"}, headers=_HOST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "calendar": "3",
        "time_working_hours": {"Mon": [8, 9]},
        "time_vacation_days": {"1": {"1": "Confraternização"}},
        "time_vacation_days_one_time": {"2026": {"12": {"25": "Natal 2026"}}},
        # T-R13.2 — `None` porque este calendário não tem nome gravado. A
        # leitura do nome é separada e tolerante de propósito: um calendário
        # sem nome não pode derrubar a leitura da jornada e dos feriados, que
        # é o que a tela precisa.
        "name": None,
    }


@pytest.mark.asyncio
async def test_calendar_put_composed_happy_path_audits(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    _FakeSysConfig().install(monkeypatch)

    transport = ASGITransport(app=create_app())
    body = _valid_calendar_body()
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 200, r.text
    assert r.json() == body

    async with admin_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "znuny_calendar", AuditLog.entity_id == "default"
                )
            )
        ).scalar_one()
        assert row.actor_login == "william"
        assert row.action == "update"
        assert row.metadata_json["applied"] == [
            "TimeWorkingHours",
            "TimeVacationDays",
            "TimeVacationDaysOneTime",
        ]


@pytest.mark.asyncio
async def test_calendar_put_partial_failure_reports_applied_and_failed(
    engine, app_session_factory, monkeypatch
):
    """A jornada (1ª chamada) é gravada com sucesso; o feriado recorrente (2ª)
    falha. O feriado pontual (3ª) NUNCA deve ser chamado, e a resposta de erro
    precisa listar o que já foi aplicado e o que falhou — aplicação parcial
    precisa ser visível, não silenciosa (contrato Bloco D)."""
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)

    fake = _FakeSysConfig(
        fail_on={"TimeVacationDays": {"Error": {"ErrorMessage": "could not lock setting"}}}
    ).install(monkeypatch)

    transport = ASGITransport(app=create_app())
    body = _valid_calendar_body()
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["applied"] == ["TimeWorkingHours"]
    assert detail["failed_setting"] == "TimeVacationDays"
    assert "lock" in detail["message"]
    assert fake.sets == ["TimeWorkingHours", "TimeVacationDays"]

    # A auditoria também registra a aplicação parcial, best-effort.
    async with admin_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "znuny_calendar", AuditLog.entity_id == "default"
                )
            )
        ).scalar_one()
        assert row.metadata_json["applied"] == ["TimeWorkingHours"]
        assert row.metadata_json["failed_setting"] == "TimeVacationDays"


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


# --------------------------------------------------------------------------- #
# T5 (teste V01) — lista de calendários com o nome gravado
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_calendars_list_reads_all_names_in_one_call(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    calls: list[dict] = []

    async def post(self, url, **kw):
        if not _is_znuny_url(url):
            return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
        calls.append(kw.get("json") or {})
        names = (kw.get("json") or {}).get("Names") or []
        settings = {n: {"Name": n, "EffectiveValue": ""} for n in names}
        settings["TimeZone::Calendar3Name"]["EffectiveValue"] = "Feriados de São Paulo"
        settings["TimeZone::Calendar5Name"]["EffectiveValue"] = "  "
        return _MockResp(200, {"Settings": settings})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        assert (await c.get("/v1/admin/znuny/calendars", headers=_HOST)).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendars", headers=_HOST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body[0] == {"value": "default", "name": None}
    assert [x["value"] for x in body] == ["default"] + [str(n) for n in range(1, 10)]
    by_value = {x["value"]: x["name"] for x in body}
    assert by_value["3"] == "Feriados de São Paulo"
    # Nome vazio ou só espaços é "sem nome", não um rótulo em branco.
    assert by_value["1"] is None
    assert by_value["5"] is None
    # Uma ida ao Znuny só, com os nove nomes.
    assert len(calls) == 1
    assert calls[0]["Names"] == [f"TimeZone::Calendar{n}Name" for n in range(1, 10)]


@pytest.mark.asyncio
async def test_calendars_list_znuny_down_is_503(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)

    async def post(self, url, **kw):
        if not _is_znuny_url(url):
            return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendars", headers=_HOST)
    assert r.status_code == 503
    assert r.json()["detail"] == "znuny_unavailable"


@pytest.mark.asyncio
async def test_calendars_list_rejected_read_degrades_to_unnamed(
    engine, app_session_factory, monkeypatch
):
    """Znuny respondeu mas recusou a leitura (ex.: overlay antigo sem os nomes
    na allowlist): a lista continua saindo, sem nomes — o seletor funciona."""
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        _mock_znuny_post({"Error": {"ErrorCode": "X", "ErrorMessage": "nope"}}, 200),
    )
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/znuny/calendars", headers=_HOST)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 10
    assert all(x["name"] is None for x in r.json())


# --------------------------------------------------------------------------- #
# Teste V01 — o PUT grava só o que mudou
# --------------------------------------------------------------------------- #
_CAL3_STATE = {
    # Como o Znuny devolve: horas em texto, dia vazio presente.
    "TimeWorkingHours::Calendar3": {"Mon": ["8", "9", "10"], "Sat": []},
    "TimeVacationDays::Calendar3": {"1": {"1": "Confraternização"}},
    "TimeVacationDaysOneTime::Calendar3": {"2026": {"12": {"25": "Natal 2026"}}},
    "TimeZone::Calendar3Name": "",
}


@pytest.mark.asyncio
async def test_calendar_put_only_the_name_changed_writes_only_the_name(
    engine, app_session_factory, monkeypatch
):
    """Staging: renomear o Calendário 3 re-deployou a jornada (deploy 67),
    estourou o timeout no feriado e nunca chegou ao nome."""
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    fake = _FakeSysConfig(_CAL3_STATE).install(monkeypatch)
    body = _valid_calendar_body("3")
    body["name"] = "Feriados de São Paulo"
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 200, r.text
    assert fake.sets == ["TimeZone::Calendar3Name"]
    assert fake.state["TimeZone::Calendar3Name"] == "Feriados de São Paulo"
    assert r.json()["name"] == "Feriados de São Paulo"
    assert r.json()["time_working_hours"] == {"Mon": ["8", "9", "10"], "Sat": []}


@pytest.mark.asyncio
async def test_calendar_put_with_nothing_changed_writes_nothing(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    state = dict(_CAL3_STATE, **{"TimeZone::Calendar3Name": "Feriados de São Paulo"})
    fake = _FakeSysConfig(state).install(monkeypatch)
    body = _valid_calendar_body("3")
    body["name"] = "Feriados de São Paulo"
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=body, headers=_HOST)
    assert r.status_code == 200, r.text
    assert fake.sets == []
    async with admin_factory() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.entity == "znuny_calendar")))
            .scalars()
            .all()
        )
    assert rows == []


@pytest.mark.asyncio
async def test_calendar_put_reads_current_state_and_503_writes_nothing(
    engine, app_session_factory, monkeypatch
):
    """Znuny fora do ar na leitura do estado atual: 503 sem nenhuma gravação."""
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    sets: list[str] = []

    async def post(self, url, **kw):
        if not _is_znuny_url(url):
            return await _ORIGINAL_ASYNC_CLIENT_POST(self, url, **kw)
        if str(url).endswith("/SysConfig/Set"):
            sets.append((kw.get("json") or {}).get("Name"))
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.put("/v1/admin/znuny/calendar", json=_valid_calendar_body("3"), headers=_HOST)
    assert r.status_code == 503
    assert sets == []


# --------------------------------------------------------------------------- #
# Teste V01 / E1 — o nome de fábrica do Znuny não é um nome dado por alguém.
# --------------------------------------------------------------------------- #
def test_factory_calendar_name_counts_as_no_name():
    from gerti_sidecar.routers.admin_znuny_people import _display_calendar_name

    assert _display_calendar_name("Calendar Name 3") is None
    assert _display_calendar_name("  Calendar Name 9 ") is None
    assert _display_calendar_name("") is None
    assert _display_calendar_name(None) is None
    assert _display_calendar_name(" Feriados de São Paulo ") == "Feriados de São Paulo"
    # parecido, mas dado por alguém: fica
    assert _display_calendar_name("Calendar Name 3 SP") == "Calendar Name 3 SP"
