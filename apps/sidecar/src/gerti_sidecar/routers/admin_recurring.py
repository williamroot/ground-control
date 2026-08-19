"""/v1/admin/tenants/{id}/recurring-tasks — a agenda de atividades (T-R11.4/11.5).

*"Verificação de backup, verificação de patches, vulnerabilidades, atualização
de servidor… é uma agenda. Isso é importante também, porque é o dia a dia dos
técnicos."* (07:09)

Ele não trata isso como automação de bastidor, então a agenda tem cadastro e
tela próprios, com a **próxima ocorrência à vista** — que é a informação que o
técnico realmente usa.

`tenant_id` explícito em toda consulta: a sessão vem de `AdminSessionLocal`
(BYPASSRLS) e a policy não se aplica. Lição da Onda 3, aplicada desde o
primeiro commit desta.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.recurrence import describe, next_occurrence, occurrences_between
from gerti_sidecar.models import RecurringTask, RecurringTaskRun, Tenant

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class RecurringTaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=255)
    body: str = Field(default="", max_length=4000)
    frequency: Literal["once", "weekly", "monthly"]
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    at_time: dt.time = dt.time(8, 0)
    starts_on: dt.date
    ends_on: dt.date | None = None
    znuny_queue_name: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=200)
    type: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=100)
    customer_user_login: str = Field(max_length=255)
    # Vazio = NÃO consome contrato (suposição S4). A tela diz isso em texto.
    contract_id: str | None = None
    active: bool = True


class RecurringTaskOut(BaseModel):
    id: str
    title: str
    body: str
    frequency: str
    weekday: int | None
    day_of_month: int | None
    at_time: str
    starts_on: str
    ends_on: str | None
    znuny_queue_name: str | None
    service: str | None
    type: str | None
    priority: str | None
    customer_user_login: str
    contract_id: str | None
    active: bool
    # O que a tela realmente usa: a frase legível e a próxima data.
    schedule_label: str
    next_occurrence: str | None
    last_ticket_id: int | None = None


class AgendaEntry(BaseModel):
    task_id: str
    title: str
    date: str
    schedule_label: str
    znuny_ticket_id: int | None = None


def _parse_tenant(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


def _require_db() -> None:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")


def _out(t: RecurringTask, *, today: dt.date, last_ticket: int | None = None) -> RecurringTaskOut:
    return RecurringTaskOut(
        id=str(t.id),
        title=t.title,
        body=t.body,
        frequency=t.frequency,
        weekday=t.weekday,
        day_of_month=t.day_of_month,
        at_time=t.at_time.strftime("%H:%M"),
        starts_on=t.starts_on.isoformat(),
        ends_on=t.ends_on.isoformat() if t.ends_on else None,
        znuny_queue_name=t.znuny_queue_name,
        service=t.service,
        type=t.type,
        priority=t.priority,
        customer_user_login=t.customer_user_login,
        contract_id=str(t.contract_id) if t.contract_id else None,
        active=t.active,
        schedule_label=describe(
            frequency=t.frequency,
            weekday=t.weekday,
            day_of_month=t.day_of_month,
            at_time=t.at_time,
        ),
        next_occurrence=(
            n.isoformat()
            if t.active
            and (
                n := next_occurrence(
                    frequency=t.frequency,
                    starts_on=t.starts_on,
                    ends_on=t.ends_on,
                    weekday=t.weekday,
                    day_of_month=t.day_of_month,
                    after=today,
                )
            )
            else None
        ),
        last_ticket_id=last_ticket,
    )


@router.get("/{tenant_id}/recurring-tasks")
async def list_recurring_tasks(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[RecurringTaskOut]:
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant(tenant_id)
    today = dt.datetime.now(dt.UTC).date()
    async with db.AdminSessionLocal() as s:
        if await s.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        tasks = (
            (
                await s.execute(
                    select(RecurringTask)
                    .where(RecurringTask.tenant_id == tid)
                    .order_by(RecurringTask.title)
                )
            )
            .scalars()
            .all()
        )
        last_by_task: dict[uuid.UUID, int] = {}
        for task_id, ticket_id in (
            await s.execute(
                select(RecurringTaskRun.task_id, RecurringTaskRun.znuny_ticket_id)
                .where(RecurringTaskRun.tenant_id == tid)
                .order_by(RecurringTaskRun.occurrence_date.desc())
            )
        ).all():
            if ticket_id is not None and task_id not in last_by_task:
                last_by_task[task_id] = int(ticket_id)
    return [_out(t, today=today, last_ticket=last_by_task.get(t.id)) for t in tasks]


@router.post("/{tenant_id}/recurring-tasks", status_code=201)
async def create_recurring_task(
    tenant_id: str,
    body: RecurringTaskIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> RecurringTaskOut:
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant(tenant_id)
    _check_shape(body)
    today = dt.datetime.now(dt.UTC).date()

    async with db.AdminSessionLocal() as s:
        async with s.begin():
            if await s.get(Tenant, tid) is None:
                raise HTTPException(status_code=404, detail="tenant_not_found")
            task = RecurringTask(
                tenant_id=tid,
                created_by=admin["agent_login"],
                **_fields(body),
            )
            s.add(task)
            await s.flush()
            out = _out(task, today=today)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="recurring_task",
        entity_id=out.id,
        description=f"atividade recorrente '{body.title}' ({out.schedule_label})",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"frequency": body.frequency, "queue": body.znuny_queue_name},
    )
    return out


@router.put("/{tenant_id}/recurring-tasks/{task_id}")
async def update_recurring_task(
    tenant_id: str,
    task_id: str,
    body: RecurringTaskIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> RecurringTaskOut:
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant(tenant_id)
    try:
        task_uuid = uuid.UUID(task_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="task_not_found") from None
    _check_shape(body)
    today = dt.datetime.now(dt.UTC).date()

    async with db.AdminSessionLocal() as s:
        async with s.begin():
            task = await s.get(RecurringTask, task_uuid)
            # `tenant_id` conferido explicitamente: a sessão é BYPASSRLS, então
            # sem isto a tarefa de um cliente seria editável pela URL de outro.
            if task is None or task.tenant_id != tid:
                raise HTTPException(status_code=404, detail="task_not_found")
            for key, value in _fields(body).items():
                setattr(task, key, value)
            await s.flush()
            out = _out(task, today=today)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="recurring_task",
        entity_id=task_id,
        description=f"atividade recorrente '{body.title}' ({out.schedule_label})",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"frequency": body.frequency, "active": body.active},
    )
    return out


@router.get("/{tenant_id}/recurring-tasks/agenda")
async def agenda(
    tenant_id: str,
    days: int = 30,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[AgendaEntry]:
    """Os próximos N dias, com o chamado já gerado quando houver (T-R11.5)."""
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant(tenant_id)
    days = max(1, min(days, 180))
    today = dt.datetime.now(dt.UTC).date()
    until = today + dt.timedelta(days=days)

    async with db.AdminSessionLocal() as s:
        if await s.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        tasks = (
            (
                await s.execute(
                    select(RecurringTask).where(
                        RecurringTask.tenant_id == tid, RecurringTask.active.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        runs = {
            (task_id, occ): ticket
            for task_id, occ, ticket in (
                await s.execute(
                    select(
                        RecurringTaskRun.task_id,
                        RecurringTaskRun.occurrence_date,
                        RecurringTaskRun.znuny_ticket_id,
                    ).where(RecurringTaskRun.tenant_id == tid)
                )
            ).all()
        }

    entries: list[AgendaEntry] = []
    for t in tasks:
        label = describe(
            frequency=t.frequency,
            weekday=t.weekday,
            day_of_month=t.day_of_month,
            at_time=t.at_time,
        )
        for occ in occurrences_between(
            frequency=t.frequency,
            starts_on=t.starts_on,
            ends_on=t.ends_on,
            weekday=t.weekday,
            day_of_month=t.day_of_month,
            since=today,
            until=until,
        ):
            entries.append(
                AgendaEntry(
                    task_id=str(t.id),
                    title=t.title,
                    date=occ.isoformat(),
                    schedule_label=label,
                    znuny_ticket_id=runs.get((t.id, occ)),
                )
            )
    entries.sort(key=lambda e: (e.date, e.title))
    return entries


def _check_shape(body: RecurringTaskIn) -> None:
    """A forma precisa bater com a frequência — o banco também recusa.

    Recusar aqui dá a mensagem em português; o CHECK do banco é a rede.
    """
    if body.frequency == "weekly" and body.weekday is None:
        raise HTTPException(status_code=422, detail="escolha o dia da semana")
    if body.frequency == "monthly" and body.day_of_month is None:
        raise HTTPException(status_code=422, detail="escolha o dia do mês")
    if body.ends_on and body.ends_on < body.starts_on:
        raise HTTPException(status_code=422, detail="a data final é anterior à inicial")


def _fields(body: RecurringTaskIn) -> dict[str, Any]:
    data = body.model_dump()
    contract = data.pop("contract_id", None)
    data["contract_id"] = uuid.UUID(contract) if contract else None
    return data
