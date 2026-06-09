"""Timer do agente + busca/detalhe de tickets (Spec #1J). Todos sob get_admin_session.

Caminho admin/BYPASSRLS (agente é cross-tenant). O timer vive em gerti.agent_timer;
o stop lança em time_accounting via GI (→ #1B cobra). A busca junta o contrato
vinculado (ticket_contract_link) por ticket p/ exibir/avisar.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain.timer_service import TimerError, TimerService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import AgentTimer, Contract, TicketContractLink

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_factory() -> async_sessionmaker[AsyncSession]:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


class StartBody(BaseModel):
    znuny_ticket_id: int


class TimerIdBody(BaseModel):
    timer_id: str


class StopBody(BaseModel):
    timer_id: str
    adjust_minutes: float | None = None
    note: str | None = None


class TimerOut(BaseModel):
    id: str
    znuny_ticket_id: int
    status: str
    accumulated_seconds: int
    last_started_at: str | None
    committed_time_unit: float | None


def _out(t: AgentTimer) -> TimerOut:
    return TimerOut(
        id=str(t.id),
        znuny_ticket_id=t.znuny_ticket_id,
        status=t.status,
        accumulated_seconds=t.accumulated_seconds,
        last_started_at=t.last_started_at.isoformat() if t.last_started_at else None,
        committed_time_unit=(
            float(t.committed_time_unit) if t.committed_time_unit is not None else None
        ),
    )


@router.post("/timer/start", status_code=201, response_model=TimerOut)
async def start_timer(
    body: StartBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        t = await TimerService(s, znuny_ticket).start(
            agent_login=admin["agent_login"],
            znuny_ticket_id=body.znuny_ticket_id,
        )
        await s.commit()
        return _out(t)


@router.post("/timer/pause", response_model=TimerOut)
async def pause_timer(
    body: TimerIdBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).pause(uuid.UUID(body.timer_id))
        except TimerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await s.commit()
        return _out(t)


@router.post("/timer/resume", response_model=TimerOut)
async def resume_timer(
    body: TimerIdBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).resume(uuid.UUID(body.timer_id))
        except TimerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await s.commit()
        return _out(t)


@router.post("/timer/stop", response_model=TimerOut)
async def stop_timer(
    body: StopBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).stop(
                uuid.UUID(body.timer_id),
                adjust_minutes=body.adjust_minutes,
                note=body.note,
            )
        except TimerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ZnunyWriteError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ZnunyUnavailable as exc:
            raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
        await s.commit()
        return _out(t)


@router.get("/timer/active")
async def active_timers(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TimerOut]:
    factory = _admin_factory()
    async with factory() as s:
        rows = (
            (
                await s.execute(
                    select(AgentTimer).where(
                        AgentTimer.agent_login == admin["agent_login"],
                        AgentTimer.status != "stopped",
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_out(t) for t in rows]


@router.get("/tickets")
async def search_tickets(
    q: str | None = None,
    customer_id: str | None = None,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[dict[str, Any]]:
    try:
        rows = await znuny_ticket.agent_search(query=q, customer_id=customer_id)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    # junta contrato vinculado por ticket (BYPASSRLS, read-only)
    factory = _admin_factory()
    ids = [r.znuny_ticket_id for r in rows]
    contract_by_ticket: dict[int, dict[str, Any]] = {}
    if ids:
        async with factory() as s:
            links = (
                await s.execute(
                    select(
                        TicketContractLink.znuny_ticket_id,
                        Contract.code,
                        Contract.type,
                    )
                    .join(Contract, Contract.id == TicketContractLink.contract_id)
                    .where(TicketContractLink.znuny_ticket_id.in_(ids))
                )
            ).all()
            contract_by_ticket = {tid: {"code": code, "type": str(typ)} for tid, code, typ in links}
    return [
        {
            "znuny_ticket_id": r.znuny_ticket_id,
            "ticket_number": r.ticket_number,
            "title": r.title,
            "state": r.state,
            "customer_id": r.customer_id,
            "owner": r.owner,
            "created": r.created,
            "contract": contract_by_ticket.get(r.znuny_ticket_id),
        }
        for r in rows
    ]


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    try:
        detail = await znuny_ticket.agent_get(znuny_ticket_id=ticket_id)
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    factory = _admin_factory()
    async with factory() as s:
        row = (
            await s.execute(
                select(Contract.code, Contract.type)
                .join(TicketContractLink, TicketContractLink.contract_id == Contract.id)
                .where(TicketContractLink.znuny_ticket_id == ticket_id)
            )
        ).first()
        detail["contract"] = {"code": row[0], "type": str(row[1])} if row else None
    return detail
