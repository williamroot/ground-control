"""Cliente GI de administração genérica do Znuny (Spec #4, Blocos A e B).

Regra da spec: **o sidecar não persiste nada** de configuração do Znuny (zero
tabela nova, zero cache). Este módulo só lê/escreve ao vivo pelo webservice
custom `GertiAdmin` — mesmo webservice de `znuny_customer_admin.py` (reusa
`ZNUNY_ADMIN_WS_URL`/`ZNUNY_WS_TOKEN`), operado pelas 7 operações genéricas
descritas no plano `docs/superpowers/plans/2026-07-30-spec-4-capa-admin-znuny.md`:

  Bloco A (objetos de CRUD simples — Queue/SLA/Service/Type/State/Priority):
    AdminObjectList, AdminObjectGet, AdminObjectAdd, AdminObjectUpdate
  Bloco B (classes de CI — CMDB):
    AdminCiClassList, AdminCiClassDefinitionGet, AdminCiClassDefinitionSet

O dispatcher Perl (`AdminSpec.pm`) traduz a chave de objeto (`Object`) para
classe/método Perl por tabela hardcoded — este cliente NUNCA nomeia classe ou
método Perl, só manda a chave. A allowlist de chave de objeto é validada
NOVAMENTE no router (`routers/admin_znuny.py`) — defesa em profundidade, este
módulo não confia no chamador.

Convenção de Route (espelha `znuny_ticket.py`: uma Route por variante de
operação, sempre POST — a REST transport do GI mapeia `RequestMethod: POST`
mesmo quando o verbo HTTP do sidecar para o CONSOLE é GET/PUT):
  /AdminObject/List            (AdminObjectList)
  /AdminObject/Get             (AdminObjectGet)
  /AdminObject                 (AdminObjectAdd)
  /AdminObject/Update          (AdminObjectUpdate)
  /AdminCiClass/List           (AdminCiClassList)
  /AdminCiClass/Definition/Get (AdminCiClassDefinitionGet)
  /AdminCiClass/Definition/Set (AdminCiClassDefinitionSet)

`AgentLogin` vai em TODO corpo (leitura e escrita) — o Perl precisa do autor
real para a ação administrativa (mesmo padrão de `TimeAccountingAdd`, plano
Bloco A regra 4). `AccessToken` reusa `ZNUNY_WS_TOKEN` (fail-closed).

Erros: `ZnunyUnavailable` (transporte/timeout/HTTP 5xx) — reusado de
`znuny_customer_admin` para toda a família `znuny_*` compartilhar a mesma
hierarquia; `ZnunyWriteError` (rejeição limpa do GI, inclusive `DefinitionCheck`
reprovando em `AdminCiClassDefinitionSet`) — o router repassa a mensagem como
422.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "AdminObjectListResult",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "ci_class_definition_get",
    "ci_class_definition_set",
    "ci_class_list",
    "object_add",
    "object_get",
    "object_list",
    "object_update",
]

_TIMEOUT = 15.0

# Listas de apoio que o AdminObjectList pode devolver junto dos itens (a UI
# precisa delas para montar selects — senão o console teria que adivinhar ids).
_SUPPORT_LIST_KEYS = ("GroupList", "StateTypeList", "ValidList", "CalendarList")


@dataclass(frozen=True)
class AdminObjectListResult:
    """Resultado de `AdminObjectList`: itens do objeto + listas de apoio p/ select."""

    items: list[dict[str, Any]]
    support: dict[str, Any] = field(default_factory=dict)


async def object_list(object_key: str, *, agent_login: str) -> AdminObjectListResult:
    data = await _post("/AdminObject/List", {"Object": object_key, "AgentLogin": agent_login})
    items = list(data.get("Items") or [])
    support = {k: data[k] for k in _SUPPORT_LIST_KEYS if k in data}
    return AdminObjectListResult(items=items, support=support)


async def object_get(object_key: str, object_id: int, *, agent_login: str) -> dict[str, Any]:
    return await _post(
        "/AdminObject/Get",
        {"Object": object_key, "ID": object_id, "AgentLogin": agent_login},
    )


async def object_add(
    object_key: str, fields: dict[str, Any], *, agent_login: str
) -> dict[str, Any]:
    return await _post(
        "/AdminObject",
        {"Object": object_key, "Fields": fields, "AgentLogin": agent_login},
    )


async def object_update(
    object_key: str, object_id: int, fields: dict[str, Any], *, agent_login: str
) -> dict[str, Any]:
    return await _post(
        "/AdminObject/Update",
        {"Object": object_key, "ID": object_id, "Fields": fields, "AgentLogin": agent_login},
    )


async def ci_class_list(*, agent_login: str) -> list[dict[str, Any]]:
    data = await _post("/AdminCiClass/List", {"AgentLogin": agent_login})
    return list(data.get("Items") or [])


async def ci_class_definition_get(class_id: int, *, agent_login: str) -> dict[str, Any]:
    return await _post(
        "/AdminCiClass/Definition/Get",
        {"ClassID": class_id, "AgentLogin": agent_login},
    )


async def ci_class_definition_set(
    class_id: int, definition: dict[str, Any], *, agent_login: str
) -> dict[str, Any]:
    """Grava nova versão da definição de classe de CI.

    `DefinitionCheck` roda no lado Znuny ANTES de gravar (plano Bloco B):
    definição inválida vem de volta como corpo `Error` do GI, que `_post`
    já converte em `ZnunyWriteError` — nenhuma lógica extra aqui. Versionamento
    (`DefinitionAdd` cria versão nova, não sobrescreve) também é responsabilidade
    do Perl; este cliente só repassa.
    """
    return await _post(
        "/AdminCiClass/Definition/Set",
        {"ClassID": class_id, "Definition": definition, "AgentLogin": agent_login},
    )


def _resolve_admin_endpoint() -> tuple[str, str]:
    """(base do webservice GertiAdmin, token de acesso) — mesmo env de znuny_customer_admin."""
    base = os.environ.get("ZNUNY_ADMIN_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


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
    return data


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _error_message(data: dict[str, Any] | None) -> str:
    """Extrai uma mensagem legível do `Error` do GI (dict ou string)."""
    if not data:
        return ""
    err = data.get("Error")
    if isinstance(err, dict):
        return str(err.get("ErrorMessage") or err.get("ErrorCode") or err or "znuny error")
    if err:
        return str(err)
    return ""
