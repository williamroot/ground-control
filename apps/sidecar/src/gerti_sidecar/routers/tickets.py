# apps/sidecar/src/gerti_sidecar/routers/tickets.py
"""Tickets do portal (Spec #1E): criar / listar / detalhe / responder.

Auth = get_current_session (qualquer papel logado). Escopo por papel (#1H),
decidido em `domain.ticket_scope` (PONTO ÚNICO, compartilhado com a busca do
portal): helpdesk => 'own'; admin => 'company' — a MESMA decisão vale para a
lista, o detalhe, a resposta, o CSAT e `/v1/search` (T-R2.4: quando divergiram,
o detalhe deixava um helpdesk abrir chamado de colega da mesma empresa; a
resposta e o CSAT deixavam ele escrever/avaliar nesse chamado; a busca ainda
listava esse chamado). Guarda de posse anti-IDOR no detalhe/reply/csat (o GI
valida CustomerID e, no escopo 'own', o CustomerUserID; ZnunyWriteError
'not found' => 404, nunca 403).
Anexos via multipart no POST. RLS por tenant para gravar o link.
"""

from __future__ import annotations

import base64
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session, tenant_session_scope
from gerti_sidecar.domain.approval_service import (
    AlreadyDecided,
    ApprovalError,
    ApprovalNotFound,
    ApprovalService,
    NotAllowed,
)
from gerti_sidecar.domain.csat_service import (
    CsatAlreadyExists,
    CsatError,
    CsatService,
    TicketNotClosed,
)
from gerti_sidecar.domain.ticket_scope import own_login, ticket_scope
from gerti_sidecar.domain.ticketing_service import (
    ContractChoiceRequired,
    NoActiveContract,
    OpenTicketInput,
    QueueNotAllowed,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Tenant
from gerti_sidecar.models.enums import PortalRole

router = APIRouter(prefix="/tickets", tags=["tickets"])

_MAX_ATTACH_BYTES = 100 * 1024 * 1024  # 100 MB por arquivo (#1L)
_ALLOWED_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".txt",
    ".log",
    ".csv",
    ".zip",
    ".doc",
    ".docx",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".avi",  # vídeo (#1L)
}


class OpenedTicketOut(BaseModel):
    znuny_ticket_id: int
    ticket_number: str
    contract_id: str
    # "pending" quando o cliente exige aprovação (R7). O portal usa isto para
    # dizer ao autor que o chamado está esperando decisão, em vez de deixá-lo
    # achar que já está sendo atendido.
    approval: str | None = None


def _customer_id(request: Request) -> str:
    tenant: Tenant = request.state.tenant
    return tenant.znuny_customer_id


def _tenant_id(request: Request) -> uuid.UUID:
    tenant: Tenant = request.state.tenant
    return tenant.id


def _is_closed(state: str | None) -> bool:
    return "closed" in (state or "").lower()


@router.post("", status_code=201, response_model=OpenedTicketOut)
async def open_ticket(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    contract_id: str | None = Form(None),
    service: str | None = Form(None),
    type_: str | None = Form(None, alias="type"),
    priority: str | None = Form(None),
    # T-R5.3: o portal ainda não oferece escolha de fila (o form-meta não
    # devolve Queues), mas o campo é aceito e VALIDADO contra as filas
    # associadas ao cliente. Sem receber aqui, a guarda do serviço nunca
    # rodaria — e o 422 de "fila não associada" seria código morto.
    queue: str | None = Form(None),
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

    # R7: o cliente exige aprovação? A chave é do TENANT, resolvida aqui —
    # o portal não escolhe, ele obedece.
    tenant: Tenant = request.state.tenant
    data = OpenTicketInput(
        customer_user=session_payload["znuny_login"],
        customer_id=_customer_id(request),
        title=title,
        body=body,
        service=service,
        type_=type_,
        priority=priority,
        contract_id=contract_id,
        attachments=attachments,
        config_item_id=config_item_id,
        queue=queue,
        requires_approval=bool(getattr(tenant, "approval_required", False)),
    )
    try:
        out = await TicketingService(session, znuny_ticket).open_ticket(data)
    except ContractChoiceRequired as exc:
        raise HTTPException(status_code=422, detail="contract_required") from exc
    except NoActiveContract as exc:
        raise HTTPException(status_code=404, detail="contract_not_found") from exc
    except QueueNotAllowed as exc:
        raise HTTPException(status_code=422, detail="queue_not_allowed") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return OpenedTicketOut(
        znuny_ticket_id=out.znuny_ticket_id,
        ticket_number=out.ticket_number,
        contract_id=out.contract_id,
        approval=out.approval,
    )


@router.get("")
async def list_tickets(
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> list[dict[str, object]]:
    try:
        rows = await znuny_ticket.search_tickets(
            scope=ticket_scope(session_payload),
            customer_user=session_payload["znuny_login"],
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


# ── R7: aprovação de chamado (Onda 5) ───────────────────────────────────────


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=1000)


class ApprovalOut(BaseModel):
    znuny_ticket_id: int
    status: str
    requested_by: str
    approver_login: str | None = None
    reason: str | None = None
    created_at: str


# ORDEM IMPORTA: `/approvals` precisa ser declarada ANTES de `/{ticket_id}`.
# O FastAPI casa as rotas na ordem de registro, e `/{ticket_id}` (que é `int`)
# engoliria `/v1/tickets/approvals` devolvendo 422 — a fila de aprovação do
# portal simplesmente nunca carregaria. Coberto por
# `test_approvals_route_is_not_swallowed_by_the_ticket_id_route`.
@router.get("/approvals", response_model=list[ApprovalOut])
async def list_pending_approvals(
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ApprovalOut]:
    """A fila de aprovação do portal — o que espera decisão deste cliente."""
    rows = await ApprovalService(session, znuny_ticket).pending_for_tenant()
    return [
        ApprovalOut(
            znuny_ticket_id=r.znuny_ticket_id,
            status=r.status,
            requested_by=r.requested_by,
            approver_login=r.approver_login,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> dict[str, object]:
    try:
        # Mesma decisão de escopo da lista: papel != admin => só o próprio
        # chamado (o GI devolve 'ticket not found' => 404, nunca 403).
        d = await znuny_ticket.get_ticket(
            znuny_ticket_id=ticket_id,
            customer_id=_customer_id(request),
            customer_user=own_login(session_payload),
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc

    # Estado do CSAT (#1M): submitted+score se já respondido; senão
    # eligible = (ticket fechado AND ainda não respondido).
    async with tenant_session_scope(_tenant_id(request)) as s:
        existing = await CsatService(s, znuny_ticket).find(
            tenant_id=_tenant_id(request), znuny_ticket_id=ticket_id
        )
    if existing is not None:
        csat: dict[str, object] = {"submitted": True, "score": existing.score}
    else:
        csat = {"submitted": False, "eligible": _is_closed(d.state)}

    return {
        "znuny_ticket_id": d.znuny_ticket_id,
        "ticket_number": d.ticket_number,
        "title": d.title,
        "state": d.state,
        "priority": d.priority,
        "created": d.created,
        "contract_id": d.contract_id,
        "articles": d.articles,
        "csat": csat,
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
        # Mesma decisão de escopo da lista/detalhe: papel != admin => só responde
        # o próprio chamado. `customer_user` é o AUTOR da resposta (sempre o
        # logado); `customer_user_id` é a GUARDA de posse (None no escopo de
        # empresa). O GI devolve 'ticket not found' => 404, nunca 403.
        await znuny_ticket.reply_ticket(
            znuny_ticket_id=ticket_id,
            customer_user=session_payload["znuny_login"],
            customer_id=_customer_id(request),
            body=payload.body,
            customer_user_id=own_login(session_payload),
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {"ok": True}


class CsatIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class CsatOut(BaseModel):
    submitted: bool = True
    score: int


@router.post("/{ticket_id}/csat", status_code=201, response_model=CsatOut)
async def submit_csat(
    ticket_id: int,
    payload: CsatIn,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> CsatOut:
    try:
        # Mesma decisão de escopo da lista/detalhe: papel != admin só avalia o
        # próprio chamado. `customer_login` é quem assina a avaliação;
        # `customer_user` é a GUARDA de posse (None no escopo de empresa).
        row = await CsatService(session, znuny_ticket).submit(
            tenant_id=_tenant_id(request),
            znuny_ticket_id=ticket_id,
            customer_login=session_payload["znuny_login"],
            customer_id=_customer_id(request),
            score=payload.score,
            comment=payload.comment,
            customer_user=own_login(session_payload),
        )
    except TicketNotClosed as exc:
        raise HTTPException(status_code=422, detail="ticket_not_closed") from exc
    except CsatAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="csat_already_submitted") from exc
    except CsatError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return CsatOut(score=row.score)


@router.post("/{ticket_id}/approval", response_model=ApprovalOut)
async def decide_approval(
    ticket_id: int,
    body: ApprovalDecisionIn,
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> ApprovalOut:
    """Aprova ou reprova. **Uma vez só** — a segunda chamada é 409.

    Só papel `approver` ou `admin` decide. Chamado de outro cliente devolve
    **404**, não 403: 403 confirmaria que o chamado existe.
    """
    role = PortalRole(session_payload.get("role") or "helpdesk")
    svc = ApprovalService(session, znuny_ticket)
    try:
        approval = await svc.decide(
            znuny_ticket_id=ticket_id,
            decision=body.decision,
            approver_login=session_payload["znuny_login"],
            approver_role=role,
            reason=body.reason,
        )
    except NotAllowed as exc:
        raise HTTPException(status_code=403, detail="not_an_approver") from exc
    except AlreadyDecided as exc:
        raise HTTPException(status_code=409, detail=f"já decidido: {exc}") from exc
    except ApprovalNotFound as exc:
        raise HTTPException(status_code=404, detail="approval_not_found") from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc

    return ApprovalOut(
        znuny_ticket_id=approval.znuny_ticket_id,
        status=approval.status,
        requested_by=approval.requested_by,
        approver_login=approval.approver_login,
        reason=approval.reason,
        created_at=approval.created_at.isoformat(),
    )
