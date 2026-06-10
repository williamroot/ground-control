"""CRUD de regras de automação (console, Spec #1Q, Task 5).

GET/POST/PUT/DELETE /v1/admin/tenants/{id}/automation-rules + GET /v1/admin/automation/meta.

Tudo sob `get_admin_session` (cross-tenant). A escrita abre
`tenant_session_scope(tenant_id, factory=AdminSessionLocal)` (RLS-subject, mas
via o papel BYPASSRLS do console — preserva o padrão D16/#1G-a).

**Validação server-side** (não confia na UI): os Pydantic schemas validam
`trigger_event`, `field`/`op` das condições e `type` das ações contra as
constantes do DOMÍNIO (`automation_eval.ALLOWED_FIELDS`/`OPS`,
`automation_actions.ACTION_HANDLERS`) — fonte única de verdade. Inválido → 422.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.automation_actions import ACTION_HANDLERS
from gerti_sidecar.domain.automation_eval import ALLOWED_FIELDS, OPS
from gerti_sidecar.models import AutomationRule, Tenant
from gerti_sidecar.models.automation import TRIGGER_EVENTS

router = APIRouter(prefix="/admin", tags=["admin"])


class Condition(BaseModel):
    field: str
    op: str
    value: Any = None

    @field_validator("field")
    @classmethod
    def _field_allowed(cls, v: str) -> str:
        if v not in ALLOWED_FIELDS:
            raise ValueError(f"campo não permitido: {v}")
        return v

    @field_validator("op")
    @classmethod
    def _op_allowed(cls, v: str) -> str:
        if v not in OPS:
            raise ValueError(f"operador não permitido: {v}")
        return v


class Action(BaseModel):
    type: str
    params: dict[str, Any] = {}

    @field_validator("type")
    @classmethod
    def _type_allowed(cls, v: str) -> str:
        if v not in ACTION_HANDLERS:
            raise ValueError(f"ação não permitida: {v}")
        return v


class RuleIn(BaseModel):
    name: str
    trigger_event: str
    conditions: list[Condition] = []
    actions: list[Action] = []
    position: int = 0
    enabled: bool = True

    @field_validator("trigger_event")
    @classmethod
    def _trigger_allowed(cls, v: str) -> str:
        if v not in TRIGGER_EVENTS:
            raise ValueError(f"gatilho inválido: {v}")
        return v


class RuleOut(BaseModel):
    id: str
    name: str
    trigger_event: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    position: int
    enabled: bool


def _out(r: AutomationRule) -> RuleOut:
    return RuleOut(
        id=str(r.id),
        name=r.name,
        trigger_event=r.trigger_event,
        conditions=list(r.conditions or []),
        actions=list(r.actions or []),
        position=r.position,
        enabled=r.enabled,
    )


async def _require_tenant(tenant_id: str) -> uuid.UUID:
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    async with db.AdminSessionLocal() as s:
        found = await s.execute(select(Tenant.id).where(Tenant.id == tid))
        if found.first() is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
    return tid


@router.get("/automation/meta")
async def automation_meta(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    """Metadados para os dropdowns da UI (fonte única = constantes do domínio)."""
    return {
        "fields": sorted(ALLOWED_FIELDS),
        "ops": sorted(OPS.keys()),
        "actions": sorted(ACTION_HANDLERS.keys()),
        "trigger_events": list(TRIGGER_EVENTS),
    }


@router.get("/tenants/{tenant_id}/automation-rules")
async def list_rules(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[RuleOut]:
    tid = await _require_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rows = (
            (
                await s.execute(
                    select(AutomationRule).order_by(
                        AutomationRule.position, AutomationRule.created_at
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_out(r) for r in rows]


@router.post("/tenants/{tenant_id}/automation-rules", status_code=201)
async def create_rule(
    tenant_id: str,
    body: RuleIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> RuleOut:
    tid = await _require_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rule = AutomationRule(
            tenant_id=tid,
            name=body.name,
            trigger_event=body.trigger_event,
            conditions=[c.model_dump() for c in body.conditions],
            actions=[a.model_dump() for a in body.actions],
            position=body.position,
            enabled=body.enabled,
        )
        s.add(rule)
        await s.flush()
        return _out(rule)


@router.put("/tenants/{tenant_id}/automation-rules/{rule_id}")
async def update_rule(
    tenant_id: str,
    rule_id: str,
    body: RuleIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> RuleOut:
    tid = await _require_tenant(tenant_id)
    try:
        rid = uuid.UUID(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="rule_not_found") from exc
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rule = (
            await s.execute(select(AutomationRule).where(AutomationRule.id == rid))
        ).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="rule_not_found")
        rule.name = body.name
        rule.trigger_event = body.trigger_event
        rule.conditions = [c.model_dump() for c in body.conditions]
        rule.actions = [a.model_dump() for a in body.actions]
        rule.position = body.position
        rule.enabled = body.enabled
        await s.flush()
        return _out(rule)


@router.delete("/tenants/{tenant_id}/automation-rules/{rule_id}", status_code=204)
async def delete_rule(
    tenant_id: str,
    rule_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    tid = await _require_tenant(tenant_id)
    try:
        rid = uuid.UUID(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="rule_not_found") from exc
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rule = (
            await s.execute(select(AutomationRule).where(AutomationRule.id == rid))
        ).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="rule_not_found")
        await s.delete(rule)
    return Response(status_code=204)
