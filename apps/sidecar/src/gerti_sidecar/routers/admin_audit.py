"""GET /v1/admin/audit-logs — console: consulta a trilha de auditoria (Spec #3 V5).

`audit_log` é operacional (SEM RLS) — lida só via `AdminSessionLocal`
(BYPASSRLS). `limit` máximo 200 (422 acima disso, via `Query(le=200)`). `q`
casa (ILIKE) em `actor_login`, `entity`, `entity_id` e `description`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.models.audit_log import AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])

ActionFilter = Literal["create", "update", "delete", "login", "export"]


class AuditLogOut(BaseModel):
    id: str
    at: dt.datetime
    actor_type: str
    actor_login: str | None
    tenant_id: str | None
    action: str
    entity: str
    entity_id: str | None
    description: str
    metadata: dict[str, object]


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


def _out(row: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=str(row.id),
        at=row.at,
        actor_type=row.actor_type,
        actor_login=row.actor_login,
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        action=row.action,
        entity=row.entity,
        entity_id=row.entity_id,
        description=row.description,
        metadata=dict(row.metadata_json or {}),
    )


@router.get("/audit-logs", response_model=AuditLogListOut)
async def list_audit_logs(
    q: str | None = Query(default=None, max_length=200),
    action: ActionFilter | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    from_: dt.datetime | None = Query(default=None, alias="from"),
    to: dt.datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> AuditLogListOut:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")

    stmt = select(AuditLog)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if tenant_id is not None:
        try:
            tid = uuid.UUID(tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="tenant_id_invalido") from exc
        stmt = stmt.where(AuditLog.tenant_id == tid)
    if from_ is not None:
        stmt = stmt.where(AuditLog.at >= from_)
    if to is not None:
        stmt = stmt.where(AuditLog.at <= to)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AuditLog.actor_login).like(like),
                func.lower(AuditLog.entity).like(like),
                func.lower(AuditLog.entity_id).like(like),
                func.lower(AuditLog.description).like(like),
            )
        )

    async with db.AdminSessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            (await session.execute(stmt.order_by(AuditLog.at.desc()).limit(limit).offset(offset)))
            .scalars()
            .all()
        )
    return AuditLogListOut(
        items=[_out(r) for r in rows], total=int(total or 0), limit=limit, offset=offset
    )
