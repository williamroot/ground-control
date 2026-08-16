"""/v1/admin/tenants/{id}/queues — relacionamentos cliente↔fila (T-R5.2, R5).

*"Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso.
Então a gente tem uma fila padrão."* (04:03)

Router separado do `admin_tenants` de propósito: é o único caminho que fala com
a lista viva de filas do Znuny a cada requisição, e mantê-lo isolado deixa
explícito o que depende do Znuny estar de pé.

Todos exigem `get_admin_session` (401 sem sessão de agente) — mesmo contrato dos
outros `/v1/admin/*`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.tenant_queue_service import (
    InvalidQueueSelection,
    QueueSelection,
    TenantNotFound,
    TenantQueueService,
)
from gerti_sidecar.integrations import znuny_admin_objects as zao

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class QueueSelectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_id: int
    is_default: bool = False


class QueuesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Cap explícito: a tela é multi-seleção sobre a lista de filas do Znuny, que
    # é dezenas, não milhares. Um corpo com 10 mil itens é engano ou abuso.
    queues: list[QueueSelectionIn] = Field(default_factory=list, max_length=200)


class TenantQueueOut(BaseModel):
    queue_id: int
    queue_name: str
    is_default: bool
    group_id: int | None = None
    group_name: str | None = None


class TenantQueuesOut(BaseModel):
    queues: list[TenantQueueOut]


def _parse_tenant_id(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


def _service() -> TenantQueueService:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return TenantQueueService(db.AdminSessionLocal, zao)


@router.get("/{tenant_id}/queues")
async def get_tenant_queues(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantQueuesOut:
    tid = _parse_tenant_id(tenant_id)
    try:
        rows = await _service().list_for_tenant(tid, agent_login=admin["agent_login"])
    except TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    return TenantQueuesOut(
        queues=[
            TenantQueueOut(
                queue_id=r.znuny_queue_id,
                queue_name=r.znuny_queue_name,
                is_default=r.is_default,
                group_id=r.group_id,
                group_name=r.group_name,
            )
            for r in rows
        ]
    )


@router.put("/{tenant_id}/queues")
async def put_tenant_queues(
    tenant_id: str,
    body: QueuesIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantQueuesOut:
    """Substitui o conjunto de filas do cliente. Idempotente.

    Recusa o conjunto INTEIRO (422) se qualquer fila não existir no Znuny, ou se
    a marcação de padrão não for exatamente uma. Gravar metade de uma seleção
    seria pior do que não gravar nada.
    """
    tid = _parse_tenant_id(tenant_id)
    service = _service()

    before = []
    try:
        before = await service.list_for_tenant(tid, agent_login=admin["agent_login"])
    except TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc

    try:
        rows = await service.replace_for_tenant(
            tid,
            [QueueSelection(q.queue_id, q.is_default) for q in body.queues],
            agent_login=admin["agent_login"],
        )
    except TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    except InvalidQueueSelection as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except zao.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="tenant_queue",
        entity_id=str(tid),
        description=f"filas do cliente: {len(rows)} associada(s)",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "antes": [{"queue_id": r.znuny_queue_id, "is_default": r.is_default} for r in before],
            "depois": [{"queue_id": r.znuny_queue_id, "is_default": r.is_default} for r in rows],
        },
    )

    return TenantQueuesOut(
        queues=[
            TenantQueueOut(
                queue_id=r.znuny_queue_id,
                queue_name=r.znuny_queue_name,
                is_default=r.is_default,
                group_id=r.group_id,
                group_name=r.group_name,
            )
            for r in rows
        ]
    )
