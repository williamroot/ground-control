"""`/v1/admin/znuny/{agents,groups,calendar}` — console como capa do Znuny
(Spec #4, Blocos C e D).

O sidecar não persiste NADA disto (contrato da Spec #4): toda tela lê ao
vivo pelo GI (`znuny_admin_people`/`znuny_admin_sysconfig`) e escreve ao
vivo pelo GI. A única gravação em `gerti` é a linha de auditoria.

Bloco C (agentes/grupos) — risco médio-alto: `AdminAgentGet` NUNCA devolve
hash de senha (os DTOs de `znuny_admin_people` já filtram); mudança de
permissão (`PUT .../agents/{id}/groups`) audita o antes e o depois. Definir
senha (`POST .../agents/{id}/password`) é operação SEPARADA de
`PUT .../agents/{id}` (correção pós-revisão adversarial) — a senha nunca
aparece na resposta (204) nem na auditoria (só o fato é registrado).

Bloco D (calendário/jornada) — risco alto: forma COMPOSTA (contrato com o
console, não settings avulsos). `GET/PUT /calendar?calendar=<sufixo>` lida
com os TRÊS settings de um calendário (`TimeWorkingHours`,
`TimeVacationDays`, `TimeVacationDaysOneTime`, com ou sem sufixo
`::CalendarN`) como uma unidade só — é assim que `useWorkingHours.ts` e a
tela `/znuny/calendario` já falam, e é o Znuny quem continua sendo a única
fonte de verdade (nada disto é persistido em `gerti`).

Guardas: sufixo de calendário fora de ''/'1'..'9' -> 404, sem consultar o
Znuny. Forma inválida de qualquer um dos três valores -> 422, SEM escrever
nenhum dos três. Escrita real é sequencial (o Znuny só sabe lockar/gravar UM
setting por chamada) — se a chamada N falhar, as N-1 anteriores já foram
aplicadas no Znuny; a resposta de erro lista explicitamente o que foi
aplicado e o que falhou (aplicação parcial silenciosa faria o operador
achar que nada mudou). Allowlist e validação de forma vivem em
`znuny_admin_sysconfig` (`is_valid_calendar_suffix`, `calendar_setting_names`,
`validate_setting_shape`); o router só orquestra e monta a resposta.

Auth: `Depends(get_admin_session)` (cookie `gsid_adm`) em toda rota — sem
tenant (Znuny é uma instância só, cross-tenant por natureza).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

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


class AgentPasswordIn(BaseModel):
    """Corpo de `POST /agents/{id}/password` — operação SEPARADA e explícita
    (correção pós-revisão adversarial): definir senha NUNCA é efeito
    colateral de `PUT /agents/{id}` (`AgentUpdate` acima não tem, e nunca
    teve, um campo de senha)."""

    new_password: str = Field(min_length=8, max_length=200)


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


class CalendarPayload(BaseModel):
    """Forma COMPOSTA do contrato (espelha `CalendarPayload` de
    `useWorkingHours.ts` no console, campo a campo, em snake_case): um
    calendário inteiro — jornada + os dois tipos de feriado — numa única
    chamada. `time_working_hours`/`time_vacation_days`/
    `time_vacation_days_one_time` ficam soltos (`dict[str, Any]`) de propósito:
    quem garante a forma é `validate_setting_shape` (Bloco D), não o Pydantic
    — assim uma leitura com um valor "estranho" já gravado no Znuny não
    quebra o GET, e a mensagem de erro do PUT continua a mensagem em
    português de `CalendarSettingInvalid`, não o formato genérico do FastAPI.
    """

    calendar: str = ""
    time_working_hours: dict[str, Any] = Field(default_factory=dict)
    time_vacation_days: dict[str, Any] = Field(default_factory=dict)
    time_vacation_days_one_time: dict[str, Any] = Field(default_factory=dict)


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


@router.post("/agents/{agent_id}/password", status_code=204)
async def set_agent_password(
    agent_id: str,
    body: AgentPasswordIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    """Define a senha de um agente — operação SEPARADA de `update_agent`
    (correção pós-revisão adversarial: definir senha nunca foi, e nunca deve
    ser, um efeito colateral de salvar o cadastro). A senha NUNCA aparece na
    resposta (204 sem corpo) nem na auditoria — só o FATO é registrado.
    """
    aid = _agent_id_or_404(agent_id)
    try:
        await people_gi.set_agent_password(aid, body.new_password, agent_login=admin["agent_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_agent_password",
        entity_id=str(aid),
        description=f"Definiu senha do agente {aid}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata=None,
    )
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Bloco D — SysConfig: calendário e jornada (forma COMPOSTA)
# --------------------------------------------------------------------------- #
@router.get("/calendar")
async def get_calendar(
    calendar: str = Query(""),
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> CalendarPayload:
    if not sysconfig_gi.is_valid_calendar_suffix(calendar):
        raise HTTPException(status_code=404, detail="calendar_not_found")
    names = sysconfig_gi.calendar_setting_names(calendar)
    try:
        settings = await sysconfig_gi.get_settings(
            [names.working_hours, names.vacation_days, names.vacation_days_one_time],
            agent_login=admin["agent_login"],
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CalendarPayload(
        calendar=calendar,
        time_working_hours=settings[names.working_hours].value or {},
        time_vacation_days=settings[names.vacation_days].value or {},
        time_vacation_days_one_time=settings[names.vacation_days_one_time].value or {},
    )


@router.put("/calendar")
async def set_calendar(
    body: CalendarPayload,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> CalendarPayload:
    if not sysconfig_gi.is_valid_calendar_suffix(body.calendar):
        raise HTTPException(status_code=404, detail="calendar_not_found")
    names = sysconfig_gi.calendar_setting_names(body.calendar)

    # A ORDEM que o corpo é gravado: jornada, feriado recorrente, feriado
    # pontual. É a mesma ordem usada nas duas guardas abaixo (validação e
    # escrita), então "a chamada N" nos comentários/erros é sempre uma destas
    # três, nesta ordem.
    to_write = [
        (names.working_hours, body.time_working_hours),
        (names.vacation_days, body.time_vacation_days),
        (names.vacation_days_one_time, body.time_vacation_days_one_time),
    ]

    # Guarda #1 (contrato Bloco D): valida a FORMA dos TRÊS valores ANTES de
    # escrever qualquer um. Se qualquer um reprovar, nada é escrito — nem os
    # outros dois que estavam OK.
    for name, value in to_write:
        try:
            sysconfig_gi.validate_setting_shape(name, value)
        except sysconfig_gi.CalendarSettingInvalid as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Guarda #2: aplica em sequência. `AdminSysConfigSet` só sabe
    # lockar/atualizar/deployar UM `Name` por chamada (não existe transação
    # que abranja os três) — então se a chamada N falhar, as N-1 anteriores
    # JÁ FORAM aplicadas no Znuny e não há como desfazê-las daqui. Aplicação
    # parcial silenciosa é o pior desfecho possível nesta tela (o operador
    # reenviaria o payload inteiro achando que nada mudou, ou desistiria
    # achando que nada foi salvo quando na verdade 1 ou 2 dos 3 settings já
    # mudaram); por isso TODA falha no meio da sequência carrega, no detail
    # da resposta de erro, exatamente quais settings já foram aplicados e
    # qual foi o que falhou — best-effort também auditado, para o rastro
    # existir mesmo quando a resposta HTTP se perde no cliente.
    applied: list[str] = []
    results: dict[str, sysconfig_gi.CalendarSetting] = {}
    for name, value in to_write:
        try:
            results[name] = await sysconfig_gi.set_setting(
                name, value, agent_login=admin["agent_login"]
            )
        except (ZnunyUnavailable, ZnunyWriteError) as exc:
            status_code = 503 if isinstance(exc, ZnunyUnavailable) else 422
            await audit_service.record(
                actor_type="agent",
                actor_login=admin["agent_login"],
                tenant_id=None,
                action="update",
                entity="znuny_calendar",
                entity_id=body.calendar or "default",
                description=(
                    f"calendário {body.calendar or 'padrão'}: aplicação PARCIAL "
                    f"({len(applied)}/{len(to_write)}) — falhou em {name}"
                ),
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                metadata={
                    "calendar": body.calendar,
                    "applied": list(applied),
                    "failed_setting": name,
                    "error": str(exc),
                },
            )
            raise HTTPException(
                status_code=status_code,
                detail={
                    "message": str(exc),
                    "applied": list(applied),
                    "failed_setting": name,
                },
            ) from exc
        applied.append(name)

    out = CalendarPayload(
        calendar=body.calendar,
        time_working_hours=results[names.working_hours].value,
        time_vacation_days=results[names.vacation_days].value,
        time_vacation_days_one_time=results[names.vacation_days_one_time].value,
    )

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="znuny_calendar",
        entity_id=body.calendar or "default",
        description=f"calendário {body.calendar or 'padrão'} atualizado (jornada + feriados)",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"calendar": body.calendar, "applied": applied},
    )
    return out
