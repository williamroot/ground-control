"""`/v1/admin/znuny/*` — console como capa de administração do Znuny (Spec #4,
Blocos A e B). Todos sob `Depends(get_admin_session)`.

A regra desta spec, em uma linha: **o sidecar não persiste nada** de
configuração do Znuny. Zero tabela nova, zero cache — toda tela lê e escreve
ao vivo pelo GI (`integrations/znuny_admin_objects.py`). A única gravação no
banco `gerti` é a linha de auditoria (via `audit_service.record`, best-effort,
nunca derruba a operação).

Guardas (defesa em profundidade — o Perl valida de novo, mas não confiamos
só nele):
  • `{object}` contra a allowlist `_ALLOWED_OBJECTS` → 404 se fora dela.
  • `{id}` precisa casar `^[0-9]+$` → 404 se malformado (nunca 400/422).
  • `ZnunyUnavailable` (transporte/5xx) → 503.
  • `ZnunyWriteError` numa ESCRITA (rejeição limpa do GI, inclusive
    `DefinitionCheck` reprovando em `AdminCiClassDefinitionSet`) → 422 com a
    mensagem do Znuny repassada — o operador precisa saber por que o Znuny
    recusou.
  • `ZnunyWriteError` numa LEITURA → 404 (`_call_get`): num GET a recusa limpa
    significa "não achei". Manter 422 apagaria a distinção que a tela precisa
    fazer entre "classe não existe" e "definição inválida".
"""

from __future__ import annotations

import re
from collections.abc import Awaitable
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.integrations import znuny_admin_objects as zao

router = APIRouter(prefix="/admin/znuny", tags=["admin"])

# Bloco A do plano — mesma tabela do dispatcher Perl (AdminSpec.pm), checada
# aqui de novo: chave fora dela nunca chega a montar uma chamada GI.
#
# NOTA (Onda 2): `SystemAddress` entrou. Até a Onda 1 ele ficava de fora de
# propósito — o console só precisava dos endereços como lista de apoio da fila.
# A tela de e-mail do R9 precisa cadastrá-los, então a allowlist abriu junto,
# com teste próprio. Ela segue sendo a barreira: chave fora dela nunca monta
# chamada GI.
_ALLOWED_OBJECTS = {
    "Queue",
    "SLA",
    "Service",
    "Type",
    "State",
    "Priority",
    # Onda 2 (T-R9.2/R9): endereços de RESPOSTA. É o outro lado do par que o
    # Kleber descreve em 06:38 — a fila define por onde a resposta sai. A
    # allowlist do Perl já o expunha; abrimos aqui junto da tela de e-mail.
    "SystemAddress",
}
_ID_RE = re.compile(r"^[0-9]+$")

_T = TypeVar("_T")


def _check_object(object_key: str) -> None:
    if object_key not in _ALLOWED_OBJECTS:
        raise HTTPException(status_code=404, detail="znuny_object_not_found")


def _check_id(id_str: str) -> int:
    if not _ID_RE.match(id_str):
        raise HTTPException(status_code=404, detail="znuny_id_not_found")
    return int(id_str)


async def _call(coro: Awaitable[_T]) -> _T:
    """Espera a chamada GI mapeando as exceções failure-safe da spec."""
    try:
        return await coro
    except zao.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except zao.ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _call_get(coro: Awaitable[_T], *, not_found: str) -> _T:
    """Como `_call`, mas para LEITURA: recurso inexistente vira 404, não 422.

    A convenção do projeto é 404 para "não existe / não é seu". Num GET, o
    `ZnunyWriteError` significa que o Znuny recusou de forma limpa — para leitura,
    isso é "não achei". Manter 422 aqui apagaria a distinção que a tela precisa
    fazer entre "classe não existe" e "definição inválida" (que é o 422 legítimo
    do `DefinitionCheck`, no PUT).
    """
    try:
        return await coro
    except zao.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except zao.ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail=not_found) from exc


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------- #
# Bloco A — objetos de CRUD simples (Queue, SLA, Service, Type, State, Priority)
# --------------------------------------------------------------------------- #


@router.get("/objects/{object}")
async def list_objects(
    object: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_object(object)
    result = await _call(zao.object_list(object, agent_login=admin["agent_login"]))
    return {"items": result.items, "support": result.support}


@router.get("/objects/{object}/{id}")
async def get_object(
    object: str,
    id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_object(object)
    object_id = _check_id(id)
    return await _call_get(
        zao.object_get(object, object_id, agent_login=admin["agent_login"]),
        not_found=f"{object.lower()}_not_found",
    )


@router.post("/objects/{object}", status_code=201)
async def create_object(
    object: str,
    body: dict[str, Any],
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_object(object)
    created = await _call(zao.object_add(object, body, agent_login=admin["agent_login"]))
    created_id = created.get("ID") if isinstance(created, dict) else None
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="create",
        entity=f"znuny_{object.lower()}",
        entity_id=str(created_id) if created_id else None,
        description=f"{object} criado no Znuny",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"object": object, "fields": body},
    )
    return created


@router.put("/objects/{object}/{id}")
async def update_object(
    object: str,
    id: str,
    body: dict[str, Any],
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_object(object)
    object_id = _check_id(id)
    updated = await _call(
        zao.object_update(object, object_id, body, agent_login=admin["agent_login"])
    )
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity=f"znuny_{object.lower()}",
        entity_id=str(object_id),
        description=f"{object} #{object_id} atualizado no Znuny",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"object": object, "fields": body},
    )
    return updated


# --------------------------------------------------------------------------- #
# Bloco B — classes de CI (CMDB)
# --------------------------------------------------------------------------- #


@router.get("/ci-classes")
async def list_ci_classes(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    items = await _call(zao.ci_class_list(agent_login=admin["agent_login"]))
    return {"items": items}


@router.get("/ci-classes/{id}/definition")
async def get_ci_class_definition(
    id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    class_id = _check_id(id)
    return await _call_get(
        zao.ci_class_definition_get(class_id, agent_login=admin["agent_login"]),
        not_found="ci_class_not_found",
    )


@router.put("/ci-classes/{id}/definition")
async def set_ci_class_definition(
    id: str,
    body: dict[str, Any],
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    class_id = _check_id(id)
    result = await _call(
        zao.ci_class_definition_set(class_id, body, agent_login=admin["agent_login"])
    )
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_ci_class",
        entity_id=str(class_id),
        description=f"definição da classe de CI #{class_id} atualizada no Znuny",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"class_id": class_id},
    )
    return result
