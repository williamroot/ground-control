"""`/v1/admin/tenants/{id}/charges` — lançamentos avulsos (T-R15.3 / T-R15.2).

Deslocamento, hora extra, item de catálogo, despesa: o que a Gerti faz e cobra
fora do que o worker traz do Znuny. É também o que dá conteúdo à fatura do
contrato **livre** (`free`), o tipo criado em D-D para o cliente avulso.

Sessão de agente, `tenant_session_scope` (RLS-subject) sobre um tenant validado
por BYPASSRLS — o mesmo desenho de `admin_invoices`. O lançamento vira um
`consumption_event`, então herda glosa, ciclo, série e fatura; ver
`domain/extra_charge_service.py` para o porquê de não ser tabela nova.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.errors import ConsumptionError
from gerti_sidecar.domain.extra_charge_service import (
    ALLOWED_KINDS,
    ExtraChargeError,
    ExtraChargeService,
    NewExtraCharge,
)
from gerti_sidecar.domain.shared_pool_service import (
    NewSharedPool,
    PoolBalance,
    SharedPoolError,
    SharedPoolService,
)
from gerti_sidecar.models import ConsumptionEvent, Contract, Tenant

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class ChargeIn(BaseModel):
    contract_id: str
    kind: str = Field(description=f"um de: {', '.join(ALLOWED_KINDS)}")
    description: str
    amount_brl: float
    quantity: float = 1.0
    minutes: float = 0.0
    occurred_on: dt.date | None = None
    service_id: str | None = None


class ChargeOut(BaseModel):
    id: int
    contract_id: str
    kind: str
    occurred_at: dt.datetime
    amount_brl: float
    minutes: float
    recorded_by: str
    glosa_id: str | None = None


def _out(ev: ConsumptionEvent) -> ChargeOut:
    return ChargeOut(
        id=ev.id,
        contract_id=str(ev.contract_id),
        kind=ev.source_kind,
        occurred_at=ev.occurred_at,
        amount_brl=float(ev.billable_amount_brl),
        minutes=float(ev.billable_minutes),
        recorded_by=ev.recorded_by,
        glosa_id=str(ev.glosa_id) if ev.glosa_id else None,
    )


async def _resolve_tenant(tenant_id: str) -> uuid.UUID:
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    async with db.AdminSessionLocal() as admin_session:
        found = await admin_session.execute(select(Tenant.id).where(Tenant.id == tenant_uuid))
        if found.first() is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
    return tenant_uuid


def _uuid_or_404(value: str, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/{tenant_id}/charges", status_code=201, response_model=ChargeOut)
async def add_charge(
    tenant_id: str,
    body: ChargeIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> ChargeOut:
    tid = await _resolve_tenant(tenant_id)
    contract_uuid = _uuid_or_404(body.contract_id, "contract_not_found")
    service_uuid = _uuid_or_404(body.service_id, "service_not_found") if body.service_id else None
    async with tenant_session_scope(tid) as session:
        try:
            ev = await ExtraChargeService(session).add(
                NewExtraCharge(
                    contract_id=contract_uuid,
                    kind=body.kind,
                    description=body.description,
                    amount_brl=body.amount_brl,
                    recorded_by=admin["agent_login"],
                    occurred_on=body.occurred_on,
                    quantity=body.quantity,
                    minutes=body.minutes,
                    service_id=service_uuid,
                )
            )
        except ExtraChargeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ConsumptionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        out = _out(ev)
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="extra_charge",
        entity_id=str(out.id),
        description=f"lançamento avulso: {body.description}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "kind": body.kind,
            "amount_brl": body.amount_brl,
            "quantity": body.quantity,
            "contract_id": body.contract_id,
        },
    )
    return out


@router.get("/{tenant_id}/charges", response_model=list[ChargeOut])
async def list_charges(
    tenant_id: str,
    contract_id: str | None = None,
    limit: int = 100,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[ChargeOut]:
    """Lançamentos avulsos do cliente — só os manuais, não o que veio do Znuny.

    O filtro é por `source_ref` começando em `manual:`, que é o prefixo que o
    `ExtraChargeService` grava. Listar todo o consumo aqui misturaria as horas
    apontadas em chamado com o que a Gerti lançou à mão, e a tela existe
    justamente para conferir a segunda coisa.
    """
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        stmt = (
            select(ConsumptionEvent)
            .where(ConsumptionEvent.source_ref.like("manual:%"))
            .order_by(ConsumptionEvent.occurred_at.desc(), ConsumptionEvent.id.desc())
            .limit(max(1, min(limit, 500)))
        )
        if contract_id:
            stmt = stmt.where(
                ConsumptionEvent.contract_id == _uuid_or_404(contract_id, "contract_not_found")
            )
        rows = (await session.execute(stmt)).scalars().all()
        return [_out(ev) for ev in rows]


@router.get("/{tenant_id}/charges/kinds", response_model=list[str])
async def list_kinds(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[str]:
    """Tipos aceitos — a tela monta o seletor com isto, não com strings soltas."""
    await _resolve_tenant(tenant_id)
    return list(ALLOWED_KINDS)


@router.get("/{tenant_id}/charges/contracts", response_model=list[dict[str, str]])
async def list_chargeable_contracts(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[dict[str, str]]:
    """Contratos que aceitam lançamento, para o seletor da tela."""
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        rows = (
            (await session.execute(select(Contract).order_by(Contract.code.asc()))).scalars().all()
        )
        return [
            {
                "id": str(c.id),
                "code": c.code,
                "type": c.type.value,
                "status": c.status.value,
            }
            for c in rows
        ]


# --------------------------------------------------------------------------- #
# T-R3.2 — bolsa de crédito compartilhada
# --------------------------------------------------------------------------- #


class PoolIn(BaseModel):
    name: str
    total_amount_brl: float
    cycle_period_months: int = 1


class PoolOut(BaseModel):
    id: str
    name: str
    total_brl: float
    consumed_brl: float
    remaining_brl: float
    contract_ids: list[str]


class PoolLinkIn(BaseModel):
    contract_id: str


@router.post("/{tenant_id}/credit-pools", status_code=201, response_model=PoolOut)
async def create_pool(
    tenant_id: str,
    body: PoolIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> PoolOut:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        svc = SharedPoolService(session)
        try:
            pool = await svc.create(
                NewSharedPool(
                    name=body.name,
                    total_amount_brl=body.total_amount_brl,
                    cycle_period_months=body.cycle_period_months,
                )
            )
            out = _pool_out(await svc.balance(pool.id))
        except SharedPoolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="shared_credit_pool",
        entity_id=out.id,
        description=f"bolsa de crédito {body.name} criada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"total_amount_brl": body.total_amount_brl},
    )
    return out


def _pool_out(balance: PoolBalance) -> PoolOut:
    return PoolOut(
        id=str(balance.pool_id),
        name=balance.name,
        total_brl=balance.total_brl,
        consumed_brl=balance.consumed_brl,
        remaining_brl=balance.remaining_brl,
        contract_ids=[str(cid) for cid in balance.contract_ids],
    )


@router.get("/{tenant_id}/credit-pools", response_model=list[PoolOut])
async def list_pools(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[PoolOut]:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        svc = SharedPoolService(session)
        return [_pool_out(await svc.balance(p.id)) for p in await svc.all_pools()]


@router.post("/{tenant_id}/credit-pools/{pool_id}/contracts", response_model=PoolOut)
async def link_contract(
    tenant_id: str,
    pool_id: str,
    body: PoolLinkIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> PoolOut:
    tid = await _resolve_tenant(tenant_id)
    pid = _uuid_or_404(pool_id, "pool_not_found")
    cid = _uuid_or_404(body.contract_id, "contract_not_found")
    async with tenant_session_scope(tid) as session:
        svc = SharedPoolService(session)
        try:
            await svc.link(pid, cid)
            out = _pool_out(await svc.balance(pid))
        except SharedPoolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="contract",
        entity_id=body.contract_id,
        description="contrato ligado à bolsa de crédito compartilhada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"pool_id": pool_id},
    )
    return out


@router.delete("/{tenant_id}/credit-pools/{pool_id}/contracts/{contract_id}", status_code=204)
async def unlink_contract(
    tenant_id: str,
    pool_id: str,
    contract_id: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    tid = await _resolve_tenant(tenant_id)
    _uuid_or_404(pool_id, "pool_not_found")
    cid = _uuid_or_404(contract_id, "contract_not_found")
    async with tenant_session_scope(tid) as session:
        try:
            await SharedPoolService(session).unlink(cid)
        except SharedPoolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="contract",
        entity_id=contract_id,
        description="contrato desligado da bolsa de crédito compartilhada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"pool_id": pool_id},
    )
    # 204 não pode ter corpo — devolver `None` faz o FastAPI recusar a rota
    # na montagem do app (o erro aparece na coleção dos testes, não aqui).
    return Response(status_code=204)
