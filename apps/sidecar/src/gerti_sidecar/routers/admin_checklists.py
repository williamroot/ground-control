"""`/v1/admin/checklists/*` e `/v1/admin/tickets/{id}/checklists` — R13b.

*"Temos aqui configurações de feriados, checklists personalizáveis."* — 08:16

Duas superfícies:

- **Modelos** (`/admin/checklists/templates`) — procedimento da Gerti, global.
  Criar e desativar é do console.
- **Execução** (`/admin/tickets/{id}/checklists`) — o modelo aplicado a um
  chamado, e o chamado é de um cliente.

**O tenant sai do CHAMADO, nunca do corpo da requisição.** O `CustomerID` vem
do Znuny e resolve o cliente; aceitar um `tenant_id` informado deixaria um
agente escrever checklist no chamado de qualquer cliente. O `tenant_id` é então
passado explicitamente ao serviço, que o coloca no WHERE — a RLS não protege
aqui, porque o console usa o papel com BYPASSRLS (lição da Onda 3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.checklist_service import (
    ChecklistError,
    ChecklistNotFound,
    ChecklistTemplateService,
    NewTemplate,
    TicketChecklistService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_admin_objects import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Tenant, TicketChecklist

router = APIRouter(prefix="/admin", tags=["admin"])


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    items: list[str] = Field(default_factory=list)


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str | None
    active: bool
    items: list[str]


class ApplyIn(BaseModel):
    template_id: str


class ChecklistItemOut(BaseModel):
    id: str
    text: str
    done: bool
    done_by: str | None
    done_at: dt.datetime | None


class ChecklistOut(BaseModel):
    id: str
    template_name: str
    applied_by: str
    applied_at: dt.datetime
    total: int
    done: int
    percent: int
    items: list[ChecklistItemOut]


class ItemIn(BaseModel):
    done: bool


def _admin_factory() -> async_sessionmaker[AsyncSession]:
    factory = db.AdminSessionLocal
    if factory is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return factory


def _uuid_or_404(value: str, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


async def _tenant_of_ticket(ticket_id: int) -> uuid.UUID:
    """Resolve o cliente A PARTIR do chamado — nunca do corpo da requisição.

    Aceitar um `tenant_id` informado deixaria um agente escrever checklist no
    chamado de qualquer cliente.
    """
    try:
        detail = await znuny_ticket.agent_get(znuny_ticket_id=ticket_id)
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    customer_id = str(detail.get("CustomerID") or "")
    if not customer_id:
        raise HTTPException(status_code=404, detail="ticket_without_customer")
    async with _admin_factory()() as s:
        tid = (
            await s.execute(select(Tenant.id).where(Tenant.znuny_customer_id == customer_id))
        ).scalar_one_or_none()
    if tid is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return uuid.UUID(str(tid))


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #


@router.get("/checklists/templates", response_model=list[TemplateOut])
async def list_templates(
    include_inactive: bool = False,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TemplateOut]:
    async with _admin_factory()() as s:
        svc = ChecklistTemplateService(s)
        rows = await (svc.list_all() if include_inactive else svc.list_active())
        return [
            TemplateOut(
                id=str(t.id),
                name=t.name,
                description=t.description,
                active=t.active,
                items=[i.text for i in await svc.items_of(t.id)],
            )
            for t in rows
        ]


@router.post("/checklists/templates", status_code=201, response_model=TemplateOut)
async def create_template(
    body: TemplateIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TemplateOut:
    async with _admin_factory()() as s:
        svc = ChecklistTemplateService(s)
        try:
            template = await svc.create(
                NewTemplate(name=body.name, items=body.items, description=body.description),
                by=admin["agent_login"],
            )
        except ChecklistError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        out = TemplateOut(
            id=str(template.id),
            name=template.name,
            description=template.description,
            active=template.active,
            items=[i.text for i in await svc.items_of(template.id)],
        )
        await s.commit()
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="create",
        entity="checklist_template",
        entity_id=out.id,
        description=f"modelo de checklist {out.name!r} criado com {len(out.items)} itens",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"items": len(out.items)},
    )
    return out


@router.delete("/checklists/templates/{template_id}", response_model=TemplateOut)
async def deactivate_template(
    template_id: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TemplateOut:
    """Desativa — nunca apaga, para não sumir com o histórico de execuções."""
    tid = _uuid_or_404(template_id, "template_not_found")
    async with _admin_factory()() as s:
        svc = ChecklistTemplateService(s)
        try:
            template = await svc.deactivate(tid)
        except ChecklistNotFound as exc:
            raise HTTPException(status_code=404, detail="template_not_found") from exc
        out = TemplateOut(
            id=str(template.id),
            name=template.name,
            description=template.description,
            active=template.active,
            items=[i.text for i in await svc.items_of(template.id)],
        )
        await s.commit()
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="delete",
        entity="checklist_template",
        entity_id=out.id,
        description=f"modelo de checklist {out.name!r} desativado",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={},
    )
    return out


# --------------------------------------------------------------------------- #
# Execução no chamado
# --------------------------------------------------------------------------- #


async def _render(svc: TicketChecklistService, checklists: list[Any]) -> list[ChecklistOut]:
    out: list[ChecklistOut] = []
    for cl in checklists:
        items = await svc.items_of(cl.id)
        progress = await svc.progress(cl.id)
        out.append(
            ChecklistOut(
                id=str(cl.id),
                template_name=cl.template_name,
                applied_by=cl.applied_by,
                applied_at=cl.applied_at,
                total=progress.total,
                done=progress.done,
                percent=progress.percent,
                items=[
                    ChecklistItemOut(
                        id=str(i.id),
                        text=i.text,
                        done=i.done,
                        done_by=i.done_by,
                        done_at=i.done_at,
                    )
                    for i in items
                ],
            )
        )
    return out


@router.get("/tickets/{ticket_id}/checklists", response_model=list[ChecklistOut])
async def list_ticket_checklists(
    ticket_id: int,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[ChecklistOut]:
    tenant_id = await _tenant_of_ticket(ticket_id)
    async with tenant_session_scope(tenant_id, factory=db.AdminSessionLocal) as s:
        svc = TicketChecklistService(s, tenant_id)
        return await _render(svc, await svc.for_ticket(ticket_id))


@router.post("/tickets/{ticket_id}/checklists", status_code=201, response_model=ChecklistOut)
async def apply_checklist(
    ticket_id: int,
    body: ApplyIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> ChecklistOut:
    tenant_id = await _tenant_of_ticket(ticket_id)
    template_id = _uuid_or_404(body.template_id, "template_not_found")
    async with tenant_session_scope(tenant_id, factory=db.AdminSessionLocal) as s:
        svc = TicketChecklistService(s, tenant_id)
        try:
            checklist = await svc.apply(
                znuny_ticket_id=ticket_id,
                template_id=template_id,
                by=admin["agent_login"],
            )
        except ChecklistNotFound as exc:
            raise HTTPException(status_code=404, detail="template_not_found") from exc
        except ChecklistError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        rendered = (await _render(svc, [checklist]))[0]
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tenant_id,
        action="create",
        entity="ticket_checklist",
        entity_id=rendered.id,
        description=f"checklist {rendered.template_name!r} aplicado ao chamado #{ticket_id}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"ticket_id": ticket_id},
    )
    return rendered


@router.put("/tickets/{ticket_id}/checklist-items/{item_id}", response_model=ChecklistOut)
async def set_item(
    ticket_id: int,
    item_id: str,
    body: ItemIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> ChecklistOut:
    """Marca/desmarca um item.

    O item é procurado com o `tenant_id` do CHAMADO no WHERE: item de outro
    cliente devolve **404**, não 403 — 403 confirmaria que ele existe.
    """
    tenant_id = await _tenant_of_ticket(ticket_id)
    iid = _uuid_or_404(item_id, "item_not_found")
    async with tenant_session_scope(tenant_id, factory=db.AdminSessionLocal) as s:
        svc = TicketChecklistService(s, tenant_id)
        try:
            item = await svc.set_item(iid, done=body.done, by=admin["agent_login"])
        except ChecklistNotFound as exc:
            raise HTTPException(status_code=404, detail="item_not_found") from exc
        checklist = await s.get(TicketChecklist, item.checklist_id)
        if checklist is None:  # pragma: no cover - FK garante
            raise HTTPException(status_code=404, detail="checklist_not_found")
        return (await _render(svc, [checklist]))[0]
