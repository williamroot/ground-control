"""Cliente GI de agentes/grupos do Znuny (Spec #4, Bloco C).

Mesmo padrão de `znuny_customer_admin.py`/`znuny_admin_sysconfig.py`:
webservice `GertiAdmin` (base `ZNUNY_ADMIN_WS_URL`), `AccessToken` =
`ZNUNY_WS_TOKEN` no corpo JSON. Rotas/campos espelham EXATAMENTE a
implementação irmã em
`znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/`:
`AdminAgentList.pm`, `AdminAgentGet.pm`, `AdminAgentSet.pm`,
`AdminGroupList.pm`, `AdminAgentGroupSet.pm`.

Pontos do contrato Perl que moldam este cliente:
  • Toda operação exige `AgentLogin` no corpo (o Perl resolve o UserID real
    do operador que está agindo — guarda "atribuição" do contrato: ação
    administrativa sem autor identificado não entra).
  • O id do agente-alvo viaja como `TargetUserID` (não `UserID`).
  • `AdminAgentSet` cria OU atualiza (presença de `TargetUserID` decide);
    resposta vem embrulhada em `{Action, Agent: {...}}`.
  • `AdminAgentGroupSet` devolve `Before`/`After` como listas de
    `{GroupID, Name}` — os DOIS estados completos, não um flag — e o
    anti-lockout (agente não pode se remover do grupo `admin`) já é
    recusado no Perl (`AdminAgentGroupSet.AntiLockout` -> `ZnunyWriteError`).

Regra inegociável (Bloco C): **nunca devolver hash de senha**. O Perl já
filtra `UserPw`/qualquer chave `/pw/i`, mas `_strip_secrets` repete o filtro
aqui — defesa em profundidade, não confiança mútua.

`set_agent_password` (correção pós-revisão adversarial) é operação SEPARADA
de `update_agent` — nunca um efeito colateral de salvar o cadastro. Espelha
`AdminAgentSetPassword.pm` (Route `/Agent/SetPassword`): `AgentLogin` (autor)
+ `TargetUserID` + `NewPassword`. A senha nunca é ecoada de volta (a resposta
do Perl só traz `{Success, UserID, UserLogin}`) e esta função não a loga nem
a devolve — só confirma o sucesso.

O sidecar não persiste nada disto (Spec #4): estas funções só leem/escrevem
o Znuny ao vivo; a única gravação em `gerti` é a linha de auditoria, feita
pelo router.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "Agent",
    "AgentGroupsChange",
    "Group",
    "GroupMembership",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "create_agent",
    "get_agent",
    "list_agents",
    "list_groups",
    "set_agent_groups",
    "set_agent_password",
    "update_agent",
]

_TIMEOUT = 10.0


@dataclass(frozen=True)
class Agent:
    id: int
    login: str
    first_name: str
    last_name: str
    email: str
    valid: bool


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    comment: str
    valid: bool


@dataclass(frozen=True)
class GroupMembership:
    id: int
    name: str


@dataclass(frozen=True)
class AgentGroupsChange:
    """Resultado de `set_agent_groups` — o GI devolve os dois estados
    (re-lidos do Znuny após a escrita, nunca só ecoados de volta).

    O router audita `before`/`after` (não só "atualizou") — guarda
    inegociável do Bloco C para a ação mais perigosa desta spec.
    """

    agent_id: int
    before: list[GroupMembership]
    after: list[GroupMembership]


def _resolve_admin_endpoint() -> tuple[str, str]:
    base = os.environ.get("ZNUNY_ADMIN_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


def _looks_like_secret(key: str) -> bool:
    lowered = key.lower()
    return "pw" in lowered or "password" in lowered


def _strip_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Remove qualquer chave que pareça senha/hash — nunca chega ao DTO."""
    return {k: v for k, v in data.items() if not _looks_like_secret(k)}


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST failure-safe para uma Route do GertiAdmin (espelha znuny_customer_admin._post)."""
    base, token = _resolve_admin_endpoint()
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    if resp.status_code >= 400:
        message = _error_message(_safe_json(resp)) or f"znuny http {resp.status_code}"
        raise ZnunyWriteError(message)
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_error_message(data) or "znuny rejeitou a operação")
    return _strip_secrets(data)


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _error_message(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    err = data.get("Error")
    if isinstance(err, dict):
        return str(err.get("ErrorMessage") or err.get("ErrorCode") or err or "znuny error")
    if err:
        return str(err)
    return ""


def _valid_id_is_one(valid_id: Any) -> bool:
    if valid_id is None:
        return False
    try:
        return int(valid_id) == 1
    except (TypeError, ValueError):
        return False


def _agent_from(data: dict[str, Any]) -> Agent:
    scrubbed = _strip_secrets(data)
    valid = _valid_id_is_one(scrubbed.get("ValidID"))
    return Agent(
        id=int(scrubbed.get("UserID") or 0),
        login=str(scrubbed.get("UserLogin") or ""),
        first_name=str(scrubbed.get("UserFirstname") or ""),
        last_name=str(scrubbed.get("UserLastname") or ""),
        email=str(scrubbed.get("UserEmail") or ""),
        valid=valid,
    )


async def list_agents(*, agent_login: str) -> list[Agent]:
    data = await _post("/Agent/List", {"AgentLogin": agent_login})
    rows = data.get("Agents") or []
    return [_agent_from(r) for r in rows if isinstance(r, dict) and r.get("UserID")]


async def get_agent(agent_id: int, *, agent_login: str) -> Agent:
    data = await _post("/Agent/Get", {"AgentLogin": agent_login, "TargetUserID": agent_id})
    if not data.get("UserID"):
        raise ZnunyWriteError("agente não encontrado")
    return _agent_from(data)


async def create_agent(
    *,
    login: str,
    first_name: str,
    last_name: str,
    email: str,
    valid: bool = True,
    agent_login: str,
) -> Agent:
    data = await _post(
        "/Agent/Set",
        {
            "AgentLogin": agent_login,
            "UserLogin": login,
            "UserFirstname": first_name,
            "UserLastname": last_name,
            "UserEmail": email,
            "ValidID": 1 if valid else 2,
        },
    )
    agent = data.get("Agent")
    if not isinstance(agent, dict):
        raise ZnunyUnavailable("resposta inesperada do Znuny")
    return _agent_from(agent)


async def update_agent(
    agent_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    valid: bool = True,
    agent_login: str,
) -> Agent:
    """Atualiza cadastro. `UserLogin` deliberadamente OMITIDO do corpo: o Perl
    (`AdminAgentSet.pm`) faz merge parcial sobre o registro atual quando um
    campo não vem na requisição — login não é editável por esta tela.
    """
    data = await _post(
        "/Agent/Set",
        {
            "AgentLogin": agent_login,
            "TargetUserID": agent_id,
            "UserFirstname": first_name,
            "UserLastname": last_name,
            "UserEmail": email,
            "ValidID": 1 if valid else 2,
        },
    )
    agent = data.get("Agent")
    if not isinstance(agent, dict):
        raise ZnunyUnavailable("resposta inesperada do Znuny")
    return _agent_from(agent)


async def set_agent_password(agent_id: int, new_password: str, *, agent_login: str) -> None:
    """Define a senha de um agente — operação SEPARADA e explícita (nunca um
    efeito colateral de `update_agent`). Espelha `AdminAgentSetPassword.pm`.

    Não devolve nada além de confirmação: a senha nunca é ecoada de volta
    pelo Perl, e esta função não a repassa, não a loga.
    """
    await _post(
        "/Agent/SetPassword",
        {"AgentLogin": agent_login, "TargetUserID": agent_id, "NewPassword": new_password},
    )


def _group_from(data: dict[str, Any]) -> Group:
    return Group(
        id=int(data.get("GroupID") or 0),
        name=str(data.get("Name") or ""),
        comment=str(data.get("Comment") or ""),
        valid=_valid_id_is_one(data.get("ValidID")),
    )


async def list_groups(*, agent_login: str) -> list[Group]:
    data = await _post("/Group/List", {"AgentLogin": agent_login})
    rows = data.get("Groups") or []
    return [_group_from(r) for r in rows if isinstance(r, dict) and r.get("GroupID")]


def _memberships(rows: Any) -> list[GroupMembership]:
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("GroupID") is not None:
            out.append(GroupMembership(id=int(r["GroupID"]), name=str(r.get("Name") or "")))
    return out


async def set_agent_groups(
    agent_id: int, group_ids: list[int], *, agent_login: str
) -> AgentGroupsChange:
    data = await _post(
        "/Agent/Group/Set",
        {"AgentLogin": agent_login, "TargetUserID": agent_id, "GroupIDs": group_ids},
    )
    before = _memberships(data.get("Before"))
    after = _memberships(data.get("After"))
    return AgentGroupsChange(agent_id=agent_id, before=before, after=after)
