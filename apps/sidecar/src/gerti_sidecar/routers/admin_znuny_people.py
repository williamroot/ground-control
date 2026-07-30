"""`/v1/admin/znuny/{agents,groups,calendar}` — console como capa do Znuny
(Spec #4, Blocos C e D).

O sidecar não persiste NADA disto (contrato da Spec #4): toda tela lê ao
vivo pelo GI (`znuny_admin_people`/`znuny_admin_sysconfig`) e escreve ao
vivo pelo GI. A única gravação em `gerti` é a linha de auditoria.

Bloco C (agentes/grupos) — risco médio-alto: `AdminAgentGet` NUNCA devolve
hash de senha (os DTOs de `znuny_admin_people` já filtram); mudança de
permissão (`PUT .../agents/{id}/groups`) audita o antes e o depois.

Bloco D (calendário/jornada) — risco alto: allowlist fechada de settings
(nome fora dela -> 404, sem consultar o Znuny) e validação de forma antes de
escrever (forma errada -> 422, sem tocar no Znuny). Ambas as guardas vivem
em `znuny_admin_sysconfig` (allowlist + `validate_setting_shape`); o router
só orquestra.

Auth: `Depends(get_admin_session)` (cookie `gsid_adm`) em toda rota — sem
tenant (Znuny é uma instância só, cross-tenant por natureza).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.integrations import znuny_admin_people as people_gi
from gerti_sidecar.integrations import znuny_admin_sysconfig as sysconfig_gi
from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

router = APIRouter(prefix="/admin/znuny", tags=["admin"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AgentOut(BaseModel):
    id: int
    login: str
    first_name: str
    last_name: str
    email: str
    valid: bool


class AgentCreate(BaseModel):
    login: str
    first_name: str
    last_name: str
    email: str
    valid: bool = True


class AgentUpdate(BaseModel):
    first_name: str
    last_name: str
    email: str
    valid: bool = True


class GroupOut(BaseModel):
    id: int
    name: str
    comment: str
    valid: bool


class AgentGroupsIn(BaseModel):
    group_ids: list[int] = []


class GroupMembershipOut(BaseModel):
    id: int
    name: str


class AgentGroupsOut(BaseModel):
    agent_id: int
    before: list[GroupMembershipOut]
    after: list[GroupMembershipOut]


class CalendarSettingOut(BaseModel):
    setting: str
    value: Any


class CalendarSettingIn(BaseModel):
    setting: str
    value: Any


def _agent_out(a: people_gi.Agent) -> AgentOut:
    return AgentOut(
        id=a.id,
        login=a.login,
        first_name=a.first_name,
        last_name=a.last_name,
        email=a.email,
        valid=a.valid,
    )


def _group_out(g: people_gi.Group) -> GroupOut:
    return GroupOut(id=g.id, name=g.name, comment=g.comment, valid=g.valid)


def _agent_id_or_404(agent_id: str) -> int:
    """Guard numérico do path param -> 404 (nunca 400/403), padrão do sidecar."""
    try:
        return int(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="agent_not_found") from exc


# --------------------------------------------------------------------------- #
# Bloco C — agentes e grupos
# --------------------------------------------------------------------------- #
@router.get("/agents")
async def list_agents(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[AgentOut]:
    try:
        agents = await people_gi.list_agents(agent_login=admin["agent_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_agent_out(a) for a in agents]


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> AgentOut:
    aid = _agent_id_or_404(agent_id)
    try:
        agent = await people_gi.get_agent(aid, agent_login=admin["agent_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _agent_out(agent)


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreate,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> AgentOut:
    try:
        agent = await people_gi.create_agent(
            login=body.login,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            valid=body.valid,
            agent_login=admin["agent_login"],
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    out = _agent_out(agent)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="create",
        entity="znuny_agent",
        entity_id=str(out.id),
        description=f"agente Znuny criado: {out.login}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"login": out.login, "email": out.email, "valid": out.valid},
    )
    return out


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> AgentOut:
    aid = _agent_id_or_404(agent_id)
    try:
        agent = await people_gi.update_agent(
            aid,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            valid=body.valid,
            agent_login=admin["agent_login"],
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    out = _agent_out(agent)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_agent",
        entity_id=str(out.id),
        description=f"agente Znuny atualizado: {out.login}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"login": out.login, "email": out.email, "valid": out.valid},
    )
    return out


@router.get("/groups")
async def list_groups(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[GroupOut]:
    try:
        groups = await people_gi.list_groups(agent_login=admin["agent_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_group_out(g) for g in groups]


@router.put("/agents/{agent_id}/groups")
async def set_agent_groups(
    agent_id: str,
    body: AgentGroupsIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> AgentGroupsOut:
    aid = _agent_id_or_404(agent_id)
    try:
        change = await people_gi.set_agent_groups(
            aid, body.group_ids, agent_login=admin["agent_login"]
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    before_out = [GroupMembershipOut(id=m.id, name=m.name) for m in change.before]
    after_out = [GroupMembershipOut(id=m.id, name=m.name) for m in change.after]

    # Ação mais perigosa do Bloco C: audita o ANTES e o DEPOIS, não só "atualizou".
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_agent_groups",
        entity_id=str(aid),
        description=f"grupos do agente Znuny {aid} alterados",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "before": [m.model_dump() for m in before_out],
            "after": [m.model_dump() for m in after_out],
        },
    )
    return AgentGroupsOut(agent_id=change.agent_id, before=before_out, after=after_out)


# --------------------------------------------------------------------------- #
# Bloco D — SysConfig: calendário e jornada
# --------------------------------------------------------------------------- #
@router.get("/calendar")
async def get_calendar_setting(
    setting: str = Query(...),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> CalendarSettingOut:
    if setting not in sysconfig_gi.ALLOWED_SETTINGS:
        raise HTTPException(status_code=404, detail="setting_not_found")
    try:
        result = await sysconfig_gi.get_setting(setting)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CalendarSettingOut(setting=result.name, value=result.value)


@router.put("/calendar")
async def set_calendar_setting(
    body: CalendarSettingIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> CalendarSettingOut:
    if body.setting not in sysconfig_gi.ALLOWED_SETTINGS:
        raise HTTPException(status_code=404, detail="setting_not_found")
    try:
        sysconfig_gi.validate_setting_shape(body.setting, body.value)
    except sysconfig_gi.CalendarSettingInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = await sysconfig_gi.set_setting(
            body.setting, body.value, agent_login=admin["agent_login"]
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_calendar",
        entity_id=body.setting,
        description=f"setting de calendário atualizado: {body.setting}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"setting": body.setting, "value": result.value},
    )
    return CalendarSettingOut(setting=result.name, value=result.value)
