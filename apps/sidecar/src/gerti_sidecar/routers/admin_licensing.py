"""`/v1/admin/licensing/*` — o quadro de licenças da operação (R16).

*"Hoje tem sete usuários ativos, a gente tem um total de nove. Total de
clientes cadastrados, 60. Contratos ativos, 43."* (09:24)

Tudo aqui é **dado da Gerti sobre a Gerti**: nenhuma destas rotas existe no
portal do cliente, e as tabelas por baixo são `REVOKE ALL ... FROM gerti_app`
— a conexão que atende o cliente nem consegue lê-las (aceite A16.5/A16.6).

A sessão usada é a do console (`AdminSessionLocal`, BYPASSRLS) porque licença
**não** é dado de tenant: não há `tenant_id` para escopar, e forçar um
`tenant_session_scope` aqui seria teatro.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.license_service import (
    LicenseError,
    LicenseService,
    NoSeatsAvailable,
    UnknownModule,
)
from gerti_sidecar.models import AgentLicense
from gerti_sidecar.models.licensing import MODULE_LABELS, MODULES

router = APIRouter(prefix="/admin/licensing", tags=["admin"])


class OverviewOut(BaseModel):
    seats_total: int
    seats_used: int
    seats_free: int
    tenants_total: int
    contracts_active: int
    # `false` = o gate está desligado e os módulos ainda NÃO barram nada. A
    # tela precisa dizer isso: um quadro que promete controle sem controlar é
    # pior do que nenhum quadro.
    enforcement_enabled: bool


class SeatsIn(BaseModel):
    seats_total: int = Field(ge=0, le=100000)
    notes: str | None = Field(default=None, max_length=2000)


class LicenseIn(BaseModel):
    agent_login: str = Field(min_length=1, max_length=255)
    modules: list[str] = Field(default_factory=list)


class LicenseOut(BaseModel):
    agent_login: str
    active: bool
    modules: list[str]
    assigned_at: dt.datetime
    assigned_by: str | None
    revoked_at: dt.datetime | None


def _out(row: AgentLicense) -> LicenseOut:
    return LicenseOut(
        agent_login=row.agent_login,
        active=row.active,
        modules=list(row.modules or []),
        assigned_at=row.assigned_at,
        assigned_by=row.assigned_by,
        revoked_at=row.revoked_at,
    )


def _factory() -> async_sessionmaker[AsyncSession]:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


def _map(exc: LicenseError) -> HTTPException:
    # `NoSeatsAvailable` e `UnknownModule` são 422 como qualquer recusa de
    # regra — o que importa é a MENSAGEM, que carrega a contagem ou a lista de
    # módulos válidos. Um 422 mudo mandaria o operador adivinhar.
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/modules")
async def list_modules(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[dict[str, str]]:
    """Catálogo FECHADO de módulos — a tela monta o seletor com isto."""
    return [{"value": m, "label": MODULE_LABELS[m]} for m in MODULES]


@router.get("/overview", response_model=OverviewOut)
async def overview(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> OverviewOut:
    async with _factory()() as session:
        data = await LicenseService(session).overview()
    return OverviewOut(
        seats_total=data.seats_total,
        seats_used=data.seats_used,
        seats_free=data.seats_free,
        tenants_total=data.tenants_total,
        contracts_active=data.contracts_active,
        enforcement_enabled=get_settings().license_enforcement_enabled,
    )


@router.put("/seats", response_model=OverviewOut)
async def set_seats(
    body: SeatsIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> OverviewOut:
    """Ajusta o total contratado (D-A: quem define é a Gerti), com auditoria."""
    async with _factory()() as session:
        svc = LicenseService(session)
        try:
            await svc.set_seats_total(body.seats_total, by=admin["agent_login"])
        except LicenseError as exc:
            raise _map(exc) from exc
        data = await svc.overview()
        await session.commit()
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="platform_license",
        entity_id="1",
        description=f"total de licenças ajustado para {body.seats_total}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"seats_total": body.seats_total},
    )
    return OverviewOut(
        seats_total=data.seats_total,
        seats_used=data.seats_used,
        seats_free=data.seats_free,
        tenants_total=data.tenants_total,
        contracts_active=data.contracts_active,
        enforcement_enabled=get_settings().license_enforcement_enabled,
    )


@router.get("/agents", response_model=list[LicenseOut])
async def list_licenses(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[LicenseOut]:
    async with _factory()() as session:
        return [_out(row) for row in await LicenseService(session).list_all()]


@router.put("/agents", response_model=LicenseOut)
async def assign_license(
    body: LicenseIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> LicenseOut:
    """Atribui ou atualiza a licença de um agente.

    Sem seat livre é **recusa** (422 com a contagem), nunca aviso: um alerta
    ignorável transforma o teto em sugestão, e o teto é o que a Gerti fatura.
    """
    async with _factory()() as session:
        try:
            row = await LicenseService(session).assign(
                body.agent_login, body.modules, by=admin["agent_login"]
            )
        except (NoSeatsAvailable, UnknownModule, LicenseError) as exc:
            raise _map(exc) from exc
        out = _out(row)
        await session.commit()
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="update",
        entity="agent_license",
        entity_id=out.agent_login,
        description=f"licença de {out.agent_login} com os módulos {', '.join(out.modules) or '—'}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"modules": out.modules},
    )
    return out


@router.delete("/agents/{agent_login}", response_model=LicenseOut)
async def revoke_license(
    agent_login: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> LicenseOut:
    """Revoga liberando o seat. A linha fica, para o histórico."""
    async with _factory()() as session:
        row = await LicenseService(session).revoke(agent_login)
        if row is None:
            raise HTTPException(status_code=404, detail="license_not_found")
        out = _out(row)
        await session.commit()
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="delete",
        entity="agent_license",
        entity_id=agent_login,
        description=f"licença de {agent_login} revogada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={},
    )
    return out
