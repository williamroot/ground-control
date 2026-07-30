"""znuny_admin_people: cliente GI de agentes/grupos (Spec #4, Bloco C).

Mock de httpx. Cobre:
  • rotas/campos batem exatamente o contrato Perl (`/Agent/List`, `/Agent/Get`,
    `/Agent/Set`, `/Group/List`, `/Agent/Group/Set`; `AgentLogin`/`TargetUserID`).
  • NENHUMA chave que pareça senha/hash (`UserPw`, ou qualquer coisa com
    `pw`/`password`) sobrevive na saída — mesmo que o Znuny "esqueça" de
    filtrar (defesa em profundidade do sidecar).
  • `AdminAgentSet` embrulha a resposta em `{Action, Agent: {...}}`.
  • `AdminAgentGroupSet` devolve `Before`/`After` como listas completas
    {GroupID, Name} — vira `GroupMembership` nos dois lados.
  • rejeição limpa (Error / 4xx) -> ZnunyWriteError; transporte/5xx -> ZnunyUnavailable.
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations import znuny_admin_people as people

_BASE = "http://znuny/otrs/nph-genericinterface.pl/Webservice/GertiAdmin"
_TOKEN = "tok-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ZNUNY_ADMIN_WS_URL", _BASE)
    monkeypatch.setenv("ZNUNY_WS_TOKEN", _TOKEN)


class _MockResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, ValueError):
            raise self._payload
        return self._payload


def _capturing_post(status_code: int, payload):
    captured: dict = {}

    async def post(self, url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResp(status_code, payload)

    return post, captured


# --------------------------------------------------------------------------- #
# list_agents
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_agents_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Agents": [
                {
                    "UserID": 3,
                    "UserLogin": "joe",
                    "UserFirstname": "Joe",
                    "UserLastname": "Doe",
                    "UserEmail": "joe@gerti.com",
                    "ValidID": 1,
                }
            ]
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agents = await people.list_agents(agent_login="william")

    assert captured["url"] == _BASE + "/Agent/List"
    assert captured["json"]["AccessToken"] == _TOKEN
    assert captured["json"]["AgentLogin"] == "william"
    assert agents == [
        people.Agent(
            id=3, login="joe", first_name="Joe", last_name="Doe", email="joe@gerti.com", valid=True
        )
    ]


@pytest.mark.asyncio
async def test_list_agents_never_leaks_password_hash(monkeypatch):
    post, _ = _capturing_post(
        200,
        {
            "Agents": [
                {
                    "UserID": 3,
                    "UserLogin": "joe",
                    "UserFirstname": "Joe",
                    "UserLastname": "Doe",
                    "UserEmail": "joe@gerti.com",
                    "UserPw": "$2y$10$abcdefghijklmnopqrstuv",
                    "ValidID": 1,
                }
            ]
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agents = await people.list_agents(agent_login="william")

    assert len(agents) == 1
    assert not hasattr(agents[0], "UserPw")
    assert not hasattr(agents[0], "pw")
    assert "$2y$10$" not in repr(agents[0])


# --------------------------------------------------------------------------- #
# get_agent
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_agent_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "UserID": 5,
            "UserLogin": "jane",
            "UserFirstname": "Jane",
            "UserLastname": "Roe",
            "UserEmail": "jane@gerti.com",
            "ValidID": 1,
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agent = await people.get_agent(5, agent_login="william")

    assert captured["url"] == _BASE + "/Agent/Get"
    assert captured["json"]["TargetUserID"] == 5
    assert captured["json"]["AgentLogin"] == "william"
    assert agent.id == 5
    assert agent.login == "jane"


@pytest.mark.asyncio
async def test_get_agent_never_leaks_password_hash(monkeypatch):
    post, _ = _capturing_post(
        200,
        {
            "UserID": 5,
            "UserLogin": "jane",
            "UserFirstname": "Jane",
            "UserLastname": "Roe",
            "UserEmail": "jane@gerti.com",
            "UserPw": "hashed-secret-value",
            "ValidID": 1,
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agent = await people.get_agent(5, agent_login="william")

    assert "hashed-secret-value" not in repr(agent)
    assert not hasattr(agent, "UserPw")


@pytest.mark.asyncio
async def test_get_agent_not_found_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(people.ZnunyWriteError):
        await people.get_agent(999, agent_login="william")


@pytest.mark.asyncio
async def test_get_agent_error_body_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Error": {"ErrorMessage": "agent not found"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(people.ZnunyWriteError, match="agent not found"):
        await people.get_agent(999, agent_login="william")


# --------------------------------------------------------------------------- #
# create_agent / update_agent
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_agent_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Action": "created",
            "Agent": {
                "UserID": 9,
                "UserLogin": "new.agent",
                "UserFirstname": "New",
                "UserLastname": "Agent",
                "UserEmail": "new@gerti.com",
                "ValidID": 1,
            },
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agent = await people.create_agent(
        login="new.agent",
        first_name="New",
        last_name="Agent",
        email="new@gerti.com",
        agent_login="william",
    )

    assert captured["url"] == _BASE + "/Agent/Set"
    body = captured["json"]
    assert "TargetUserID" not in body
    assert body["UserLogin"] == "new.agent"
    assert body["AgentLogin"] == "william"
    assert agent.id == 9
    assert agent.login == "new.agent"


@pytest.mark.asyncio
async def test_create_agent_unexpected_response_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(200, {"Action": "created"})  # sem "Agent"
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(people.ZnunyUnavailable):
        await people.create_agent(
            login="x", first_name="X", last_name="Y", email="x@gerti.com", agent_login="william"
        )


@pytest.mark.asyncio
async def test_update_agent_happy_omits_login(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Action": "updated",
            "Agent": {
                "UserID": 9,
                "UserLogin": "new.agent",
                "UserFirstname": "Novo",
                "UserLastname": "Nome",
                "UserEmail": "new@gerti.com",
                "ValidID": 1,
            },
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    agent = await people.update_agent(
        9, first_name="Novo", last_name="Nome", email="new@gerti.com", agent_login="william"
    )

    body = captured["json"]
    assert body["TargetUserID"] == 9
    # login não é editável por esta operação — nunca enviado, o Perl mantém o atual.
    assert "UserLogin" not in body
    assert agent.first_name == "Novo"


# --------------------------------------------------------------------------- #
# list_groups
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_groups_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Groups": [
                {"GroupID": 1, "Name": "users", "Comment": "default", "ValidID": 1},
                {"GroupID": 2, "Name": "admin", "Comment": "console admins", "ValidID": 1},
            ]
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    groups = await people.list_groups(agent_login="william")

    assert captured["url"] == _BASE + "/Group/List"
    assert groups == [
        people.Group(id=1, name="users", comment="default", valid=True),
        people.Group(id=2, name="admin", comment="console admins", valid=True),
    ]


# --------------------------------------------------------------------------- #
# set_agent_groups
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_set_agent_groups_returns_before_and_after(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "UserID": 5,
            "Before": [{"GroupID": 1, "Name": "users"}],
            "After": [
                {"GroupID": 1, "Name": "users"},
                {"GroupID": 2, "Name": "admin"},
            ],
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    change = await people.set_agent_groups(5, [1, 2], agent_login="william")

    assert captured["url"] == _BASE + "/Agent/Group/Set"
    assert captured["json"]["TargetUserID"] == 5
    assert captured["json"]["GroupIDs"] == [1, 2]
    assert captured["json"]["AgentLogin"] == "william"
    assert change.before == [people.GroupMembership(id=1, name="users")]
    assert change.after == [
        people.GroupMembership(id=1, name="users"),
        people.GroupMembership(id=2, name="admin"),
    ]


@pytest.mark.asyncio
async def test_set_agent_groups_anti_lockout_raises_write_error(monkeypatch):
    post, _ = _capturing_post(
        200, {"Error": {"ErrorMessage": "you cannot remove yourself from the admin group."}}
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(people.ZnunyWriteError, match="admin group"):
        await people.set_agent_groups(5, [], agent_login="william")


# --------------------------------------------------------------------------- #
# transporte / 5xx
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_transport_error_raises_unavailable(monkeypatch):
    async def boom(self, url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    with pytest.raises(people.ZnunyUnavailable):
        await people.list_agents(agent_login="william")


@pytest.mark.asyncio
async def test_5xx_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(503, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(people.ZnunyUnavailable):
        await people.list_agents(agent_login="william")
