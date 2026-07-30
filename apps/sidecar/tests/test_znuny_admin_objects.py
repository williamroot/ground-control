"""znuny_admin_objects: cliente GI de administração genérica (Spec #4, Blocos A/B).

Mock de httpx (mesmo padrão de test_znuny_customer_admin.py):
  • happy path → URL/AccessToken/corpo corretos, retorno mapeado.
  • rejeição limpa (HTTP 4xx OU corpo com `Error`) → ZnunyWriteError, inclusive
    DefinitionCheck reprovando em ci_class_definition_set.
  • transporte / HTTP 5xx → ZnunyUnavailable.
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations import znuny_admin_objects as zao

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
# object_list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_object_list_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Items": [{"ID": 1, "Name": "Suporte"}],
            "GroupList": [{"ID": 1, "Name": "users"}],
            "ValidList": [{"ID": 1, "Name": "valid"}],
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.object_list("Queue", agent_login="william")

    assert captured["url"] == _BASE + "/AdminObject/List"
    body = captured["json"]
    assert body["AccessToken"] == _TOKEN
    assert body["Object"] == "Queue"
    assert body["AgentLogin"] == "william"
    assert out.items == [{"ID": 1, "Name": "Suporte"}]
    assert out.support["GroupList"] == [{"ID": 1, "Name": "users"}]
    assert out.support["ValidList"] == [{"ID": 1, "Name": "valid"}]
    assert "CalendarList" not in out.support


@pytest.mark.asyncio
async def test_object_list_5xx_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(503, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zao.ZnunyUnavailable):
        await zao.object_list("Queue", agent_login="william")


@pytest.mark.asyncio
async def test_object_list_transport_error_raises_unavailable(monkeypatch):
    async def boom(self, url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    with pytest.raises(zao.ZnunyUnavailable):
        await zao.object_list("Queue", agent_login="william")


# --------------------------------------------------------------------------- #
# object_get
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_object_get_happy(monkeypatch):
    post, captured = _capturing_post(200, {"ID": 3, "Name": "Faturamento"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.object_get("Queue", 3, agent_login="william")

    assert captured["url"] == _BASE + "/AdminObject/Get"
    assert captured["json"]["Object"] == "Queue"
    assert captured["json"]["ID"] == 3
    assert out == {"ID": 3, "Name": "Faturamento"}


@pytest.mark.asyncio
async def test_object_get_unknown_id_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Error": {"ErrorMessage": "queue not found"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zao.ZnunyWriteError, match="queue not found"):
        await zao.object_get("Queue", 999, agent_login="william")


# --------------------------------------------------------------------------- #
# object_add / object_update
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_object_add_happy(monkeypatch):
    post, captured = _capturing_post(200, {"ID": 9})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.object_add("SLA", {"Name": "Gold"}, agent_login="william")

    assert captured["url"] == _BASE + "/AdminObject/Add"
    body = captured["json"]
    assert body["Object"] == "SLA"
    assert body["Fields"] == {"Name": "Gold"}
    assert body["AgentLogin"] == "william"
    assert out == {"ID": 9}


@pytest.mark.asyncio
async def test_object_add_rejected_raises_write_error(monkeypatch):
    post, _ = _capturing_post(422, {"Error": {"ErrorCode": "Validation"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zao.ZnunyWriteError):
        await zao.object_add("SLA", {"Name": ""}, agent_login="william")


@pytest.mark.asyncio
async def test_object_update_happy(monkeypatch):
    post, captured = _capturing_post(200, {"ID": 3, "Name": "Faturamento 2"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.object_update("Queue", 3, {"Name": "Faturamento 2"}, agent_login="william")

    assert captured["url"] == _BASE + "/AdminObject/Update"
    body = captured["json"]
    assert body["Object"] == "Queue"
    assert body["ID"] == 3
    assert body["Fields"] == {"Name": "Faturamento 2"}
    assert out == {"ID": 3, "Name": "Faturamento 2"}


# --------------------------------------------------------------------------- #
# ci_class_list / ci_class_definition_get / ci_class_definition_set
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ci_class_list_happy(monkeypatch):
    post, captured = _capturing_post(200, {"Classes": [{"ID": 1, "Name": "Computer"}]})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.ci_class_list(agent_login="william")

    assert captured["url"] == _BASE + "/CiClass/List"
    assert captured["json"]["AgentLogin"] == "william"
    assert out == [{"ID": 1, "Name": "Computer"}]


@pytest.mark.asyncio
async def test_ci_class_definition_get_happy(monkeypatch):
    post, captured = _capturing_post(
        200, {"ClassID": 1, "DefinitionID": 4, "Definition": {"Pages": []}}
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.ci_class_definition_get(1, agent_login="william")

    assert captured["url"] == _BASE + "/CiClass/Definition/Get"
    assert captured["json"]["ClassID"] == 1
    assert out["DefinitionID"] == 4


@pytest.mark.asyncio
async def test_ci_class_definition_set_happy(monkeypatch):
    post, captured = _capturing_post(200, {"DefinitionID": 5})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zao.ci_class_definition_set(1, {"Pages": []}, agent_login="william")

    assert captured["url"] == _BASE + "/CiClass/Definition/Set"
    body = captured["json"]
    assert body["ClassID"] == 1
    assert body["Definition"] == {"Pages": []}
    assert out == {"DefinitionID": 5}


@pytest.mark.asyncio
async def test_ci_class_definition_set_check_failure_raises_write_error(monkeypatch):
    """DefinitionCheck reprovando no lado Znuny -> Error no corpo -> ZnunyWriteError."""
    post, _ = _capturing_post(
        200, {"Error": {"ErrorMessage": "DefinitionCheck failed: invalid YAML"}}
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zao.ZnunyWriteError, match="DefinitionCheck failed"):
        await zao.ci_class_definition_set(1, {"Pages": "not-a-list"}, agent_login="william")
