# apps/sidecar/src/gerti_sidecar/routers/tickets.py
"""Tickets do portal (Spec #1E): criar / listar / detalhe / responder.

Auth = get_current_session (qualquer papel logado). Escopo de listagem por papel
(#1H): helpdesk => 'own'; admin => 'company'. Guarda de posse anti-IDOR no
detalhe/reply (o GI valida CustomerID; ZnunyWriteError 'not found' => 404).
Anexos via multipart no POST. RLS por tenant para gravar o link.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.ticketing_service import (
    ContractChoiceRequired,
    NoActiveContract,
    OpenTicketInput,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Tenant
from gerti_sidecar.models.enums import PortalRole

router = APIRouter(prefix="/tickets", tags=["tickets"])

_MAX_ATTACH_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo
_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".log", ".csv", ".zip", ".doc", ".docx"}


class OpenedTicketOut(BaseModel):
    znuny_ticket_id: int
    ticket_number: str
    contract_id: str


def _customer_id(request: Request) -> str:
    tenant: Tenant = request.state.tenant
    return tenant.znuny_customer_id


@router.post("", status_code=201, response_model=OpenedTicketOut)
async def open_ticket(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    contract_id: str | None = Form(None),
    service: str | None = Form(None),
    type_: str | None = Form(None, alias="type"),
    priority: str | None = Form(None),
    config_item_id: int | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> OpenedTicketOut:
    attachments = []
    for f in files:
        raw = await f.read()
        if len(raw) > _MAX_ATTACH_BYTES:
            raise HTTPException(status_code=413, detail="attachment_too_large")
        name = f.filename or "anexo"
        ext = name[name.rfind(".") :].lower() if "." in name else ""
        if ext not in _ALLOWED_EXT:
            raise HTTPException(status_code=415, detail=f"ext_not_allowed:{ext}")
        attachments.append(
            znuny_ticket.Attachment(
                filename=name,
                content_type=f.content_type or "application/octet-stream",
                content_base64=base64.b64encode(raw).decode("ascii"),
            )
        )

    data = OpenTicketInput(
        customer_user=session_payload["customer_login"],
        customer_id=_customer_id(request),
        title=title,
        body=body,
        service=service,
        type_=type_,
        priority=priority,
        contract_id=contract_id,
        attachments=attachments,
        config_item_id=config_item_id,
    )
    try:
        out = await TicketingService(session, znuny_ticket).open_ticket(data)
    except ContractChoiceRequired as exc:
        raise HTTPException(status_code=422, detail="contract_required") from exc
    except NoActiveContract as exc:
        raise HTTPException(status_code=404, detail="contract_not_found") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return OpenedTicketOut(
        znuny_ticket_id=out.znuny_ticket_id,
        ticket_number=out.ticket_number,
        contract_id=out.contract_id,
    )


@router.get("")
async def list_tickets(
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> list[dict[str, object]]:
    scope = "company" if session_payload["role"] == PortalRole.admin.value else "own"
    try:
        rows = await znuny_ticket.search_tickets(
            scope=scope,
            customer_user=session_payload["customer_login"],
            customer_id=_customer_id(request),
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return [
        {
            "znuny_ticket_id": r.znuny_ticket_id,
            "ticket_number": r.ticket_number,
            "title": r.title,
            "state": r.state,
            "created": r.created,
            "contract_id": r.contract_id,
        }
        for r in rows
    ]


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> dict[str, object]:
    try:
        d = await znuny_ticket.get_ticket(
            znuny_ticket_id=ticket_id, customer_id=_customer_id(request)
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {
        "znuny_ticket_id": d.znuny_ticket_id,
        "ticket_number": d.ticket_number,
        "title": d.title,
        "state": d.state,
        "priority": d.priority,
        "created": d.created,
        "contract_id": d.contract_id,
        "articles": d.articles,
    }


class ReplyBody(BaseModel):
    body: str


@router.post("/{ticket_id}/reply", status_code=201)
async def reply_ticket(
    ticket_id: int,
    payload: ReplyBody,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> dict[str, object]:
    try:
        await znuny_ticket.reply_ticket(
            znuny_ticket_id=ticket_id,
            customer_user=session_payload["customer_login"],
            customer_id=_customer_id(request),
            body=payload.body,
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {"ok": True}
