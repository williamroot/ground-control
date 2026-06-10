"""/v1/admin/tenants/{id}/invoices — console (agente): gera do ciclo, paga, cancela, lista.

Spec #1P / ADR D19. Exige get_admin_session. Valida a existência do tenant via
AdminSessionLocal (BYPASSRLS), depois abre tenant_session_scope (RLS-subject) e
delega ao InvoiceService — preserva as invariantes #1C/#1P.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.errors import (
    CycleNotClosable,
    InvoiceAlreadyExists,
    InvoiceError,
)
from gerti_sidecar.domain.invoice_service import InvoiceService
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
    _admin: AdminSessionPayload = Depends(get_admin_session),
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
        return _out(inv)


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
    number: int = Path(..., ge=1),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    tenant_uuid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tenant_uuid) as session:
        inv = await _get_by_number(session, number)
        try:
            inv = await InvoiceService(session).mark_paid(inv.id)
        except InvoiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _out(inv)


@router.post("/{tenant_id}/invoices/{number}/void", response_model=InvoiceOut)
async def mark_void(
    tenant_id: str,
    number: int = Path(..., ge=1),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> InvoiceOut:
    tenant_uuid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tenant_uuid) as session:
        inv = await _get_by_number(session, number)
        try:
            inv = await InvoiceService(session).mark_void(inv.id)
        except InvoiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _out(inv)
