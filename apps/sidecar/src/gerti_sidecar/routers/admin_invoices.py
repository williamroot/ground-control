"""/v1/admin/tenants/{id}/invoices — console (agente): gera do ciclo, paga, cancela, lista.

Spec #1P / ADR D19. Exige get_admin_session. Valida a existência do tenant via
AdminSessionLocal (BYPASSRLS), depois abre tenant_session_scope (RLS-subject) e
delega ao InvoiceService — preserva as invariantes #1C/#1P.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import get_asaas_client, get_settings
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.errors import (
    CycleNotClosable,
    InvoiceAlreadyExists,
    InvoiceError,
)
from gerti_sidecar.domain.invoice_charge_service import (
    ChargingDisabled,
    ChargingRefused,
    InvoiceChargeService,
)
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.integrations.asaas_client import AsaasError, AsaasUnavailable
from gerti_sidecar.models import Invoice, Tenant

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class CreateInvoiceBody(BaseModel):
    cycle_id: str


class InvoiceOut(BaseModel):
    id: str
    number: int
    status: str
    issued_at: dt.datetime
    due_at: dt.datetime
    period_start: dt.date
    period_end: dt.date
    currency: str
    subtotal_cents: int
    total_cents: int
    # T-R15.5 — cobrança e nota. `None` quando a fatura nunca foi ao Asaas,
    # que é o caso de toda fatura enquanto ASAAS_ENABLED=false.
    asaas_payment_id: str | None = None
    asaas_charge_status: str | None = None
    bank_slip_url: str | None = None
    nfe_status: str | None = None
    nfe_pdf_url: str | None = None


def _out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=str(inv.id),
        number=inv.number,
        status=inv.status.value,
        issued_at=inv.issued_at,
        due_at=inv.due_at,
        period_start=inv.period_start,
        period_end=inv.period_end,
        currency=inv.currency,
        subtotal_cents=inv.subtotal_cents,
        total_cents=inv.total_cents,
        asaas_payment_id=inv.asaas_payment_id,
        asaas_charge_status=inv.asaas_charge_status,
        bank_slip_url=inv.asaas_bank_slip_url,
        nfe_status=inv.nfe_status,
        nfe_pdf_url=inv.nfe_pdf_url,
    )


async def _resolve_tenant(tenant_id: str) -> uuid.UUID:
    """Valida UUID + existência (cross-tenant, BYPASSRLS) → 404 tenant_not_found."""
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


@router.post("/{tenant_id}/invoices", status_code=201, response_model=InvoiceOut)
async def create_invoice_from_cycle(
    tenant_id: str,
    body: CreateInvoiceBody,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    tenant_uuid = await _resolve_tenant(tenant_id)
    try:
        cycle_uuid = uuid.UUID(body.cycle_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="cycle_not_found") from exc

    async with tenant_session_scope(tenant_uuid) as session:
        try:
            inv = await InvoiceService(session).create_from_cycle(cycle_uuid)
        except InvoiceAlreadyExists as exc:
            raise HTTPException(status_code=409, detail="invoice_already_exists") from exc
        except CycleNotClosable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvoiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        out = _out(inv)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tenant_uuid,
        action="create",
        entity="invoice",
        entity_id=out.id,
        description=f"fatura #{out.number} gerada do ciclo {body.cycle_id}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"number": out.number, "total_cents": out.total_cents},
    )
    return out


@router.get("/{tenant_id}/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    tenant_id: str,
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[InvoiceOut]:
    tenant_uuid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tenant_uuid) as session:
        rows = (
            (await session.execute(select(Invoice).order_by(Invoice.number.desc()))).scalars().all()
        )
        return [_out(r) for r in rows]


async def _get_by_number(session: AsyncSession, number: int) -> Invoice:
    inv = (
        await session.execute(select(Invoice).where(Invoice.number == number))
    ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="invoice_not_found")
    return inv


@router.post("/{tenant_id}/invoices/{number}/paid", response_model=InvoiceOut)
async def mark_paid(
    tenant_id: str,
    request: Request,
    number: int = Path(..., ge=1),
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    tenant_uuid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tenant_uuid) as session:
        inv = await _get_by_number(session, number)
        try:
            inv = await InvoiceService(session).mark_paid(inv.id)
        except InvoiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        out = _out(inv)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tenant_uuid,
        action="update",
        entity="invoice",
        entity_id=out.id,
        description=f"fatura #{number} marcada como paga",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"number": number},
    )
    return out


@router.post("/{tenant_id}/invoices/{number}/void", response_model=InvoiceOut)
async def mark_void(
    tenant_id: str,
    request: Request,
    number: int = Path(..., ge=1),
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    tenant_uuid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tenant_uuid) as session:
        inv = await _get_by_number(session, number)
        try:
            inv = await InvoiceService(session).mark_void(inv.id)
        except InvoiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        out = _out(inv)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tenant_uuid,
        action="update",
        entity="invoice",
        entity_id=out.id,
        description=f"fatura #{number} cancelada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"number": number},
    )
    return out


# --------------------------------------------------------------------------- #
# T-R15.5 — boleto e nota fiscal (Asaas)
# --------------------------------------------------------------------------- #


class NfeBody(BaseModel):
    service_description: str | None = None
    municipal_service_code: str | None = None
    municipal_service_name: str | None = None


def _charge_service(session: AsyncSession) -> InvoiceChargeService:
    settings = get_settings()
    enabled = bool(settings.asaas_enabled and settings.asaas_api_key)
    return InvoiceChargeService(
        session,
        get_asaas_client(settings) if enabled else None,
        enabled=enabled,
    )


def _map_charge_error(exc: Exception) -> HTTPException:
    """Erros do Asaas com o significado que o operador precisa ler.

    `ChargingDisabled` → 503 e não 404: o console mostra o botão e o operador
    tem de saber que falta a CHAVE, não que a rota não existe. É diferente do
    checkout público, onde 404 é proposital para não revelar o recurso.
    """
    if isinstance(exc, ChargingDisabled):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ChargingRefused):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AsaasUnavailable):
        return HTTPException(status_code=503, detail="asaas_unavailable")
    if isinstance(exc, AsaasError):
        # Recusa limpa do Asaas (conta sem configuração fiscal, documento
        # inválido). A mensagem dele é repassada de propósito: sem ela, "não
        # foi possível emitir a nota" manda o operador adivinhar.
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, InvoiceError):
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


@router.post("/{tenant_id}/invoices/{number}/charge", response_model=InvoiceOut)
async def issue_bank_slip(
    tenant_id: str,
    number: int,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    """Emite o boleto da fatura no Asaas (idempotente)."""
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        inv = await _get_by_number(session, number)
        try:
            charged = await _charge_service(session).issue_bank_slip(inv.id)
        except Exception as exc:
            raise _map_charge_error(exc) from exc
        out = _out(charged)
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        # `action` é um Literal fechado no audit_service; emitir boleto é a
        # criação de uma cobrança, e é a ENTIDADE que distingue o evento.
        action="create",
        entity="invoice_charge",
        entity_id=str(out.id),
        description=f"boleto emitido para a fatura #{number:04d}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"asaas_payment_id": out.asaas_payment_id},
    )
    return out


@router.post("/{tenant_id}/invoices/{number}/nfe", response_model=InvoiceOut)
async def issue_nfe(
    tenant_id: str,
    number: int,
    body: NfeBody,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    """Agenda a nota fiscal de serviço da fatura (exige o boleto emitido)."""
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        inv = await _get_by_number(session, number)
        try:
            issued = await _charge_service(session).issue_nfe(
                inv.id,
                service_description=body.service_description,
                municipal_service_code=body.municipal_service_code,
                municipal_service_name=body.municipal_service_name,
            )
        except Exception as exc:
            raise _map_charge_error(exc) from exc
        out = _out(issued)
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="invoice_nfe",
        entity_id=str(out.id),
        description=f"nota fiscal agendada para a fatura #{number:04d}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"nfe_id": issued.nfe_id},
    )
    return out


@router.post("/{tenant_id}/invoices/{number}/refresh", response_model=InvoiceOut)
async def refresh_charge(
    tenant_id: str,
    number: int,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    """Relê no Asaas o estado da cobrança e da nota — webhook se perde."""
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        inv = await _get_by_number(session, number)
        try:
            return _out(await _charge_service(session).refresh(inv.id))
        except Exception as exc:
            raise _map_charge_error(exc) from exc
