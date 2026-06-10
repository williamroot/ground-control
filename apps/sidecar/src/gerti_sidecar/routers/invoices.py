"""GET /v1/invoices — portal (admin do tenant): lista, detalhe, baixa PDF.

Spec #1P. require_admin a nível de router (faturas = dado financeiro, admin-only,
como contratos #1H). tenant-scoped via get_tenant_session (RLS). O PDF é gerado
on-demand se ainda não existir (busca branding do tenant), persistido em
invoice.pdf_bytes e servido como application/pdf.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session, require_admin
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.invoice_pdf import InvoiceBranding, render_invoice_pdf
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import Invoice, TenantBranding

router = APIRouter(prefix="/invoices", tags=["portal"], dependencies=[Depends(require_admin)])


class InvoiceItem(BaseModel):
    number: int
    status: str
    issued_at: dt.datetime
    due_at: dt.datetime
    period_start: dt.date
    period_end: dt.date
    currency: str
    total_cents: int


class InvoiceLineOut(BaseModel):
    description: str
    quantity: float
    unit: str
    unit_price_cents: int
    amount_cents: int


class InvoiceDetail(InvoiceItem):
    subtotal_cents: int
    lines: list[InvoiceLineOut]


def _item(inv: Invoice) -> InvoiceItem:
    return InvoiceItem(
        number=inv.number,
        status=inv.status.value,
        issued_at=inv.issued_at,
        due_at=inv.due_at,
        period_start=inv.period_start,
        period_end=inv.period_end,
        currency=inv.currency,
        total_cents=inv.total_cents,
    )


@router.get("", response_model=list[InvoiceItem])
async def list_invoices(
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[InvoiceItem]:
    rows = (await session.execute(select(Invoice).order_by(Invoice.number.desc()))).scalars().all()
    return [_item(r) for r in rows]


def _parse_number(number: str) -> int:
    """Guard numérico (^[0-9]+$): não-numérico → 404 (anti path-injection)."""
    if not number.isdigit():
        raise HTTPException(status_code=404, detail="invoice_not_found")
    return int(number)


async def _get_by_number(session: AsyncSession, number: int) -> Invoice:
    inv = (
        await session.execute(select(Invoice).where(Invoice.number == number))
    ).scalar_one_or_none()
    if inv is None:  # RLS hid cross-tenant ou não existe → 404 (nunca 403/500)
        raise HTTPException(status_code=404, detail="invoice_not_found")
    return inv


@router.get("/{number}", response_model=InvoiceDetail)
async def get_invoice(
    number: str = Path(...),
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> InvoiceDetail:
    inv = await _get_by_number(session, _parse_number(number))
    lines = await InvoiceService(session).lines_for(inv.id)
    return InvoiceDetail(
        **_item(inv).model_dump(),
        subtotal_cents=inv.subtotal_cents,
        lines=[
            InvoiceLineOut(
                description=line.description,
                quantity=float(line.quantity),
                unit=line.unit,
                unit_price_cents=line.unit_price_cents,
                amount_cents=line.amount_cents,
            )
            for line in lines
        ],
    )


async def _branding_for(session: AsyncSession) -> InvoiceBranding:
    row = (await session.execute(select(TenantBranding))).scalar_one_or_none()
    if row is None:
        return InvoiceBranding(display_name="Fatura", logo_url=None, primary_color="#334155")
    return InvoiceBranding(
        display_name=row.display_name,
        logo_url=row.logo_url,
        primary_color=row.primary_color,
    )


@router.get("/{number}/pdf")
async def get_invoice_pdf(
    number: str = Path(...),
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    inv = await _get_by_number(session, _parse_number(number))
    if inv.pdf_bytes is None:
        lines = await InvoiceService(session).lines_for(inv.id)
        branding = await _branding_for(session)
        pdf = render_invoice_pdf(inv, lines, branding)
        inv.pdf_bytes = pdf
        inv.pdf_generated_at = dt.datetime.now(dt.UTC)
        await session.flush()
    else:
        pdf = inv.pdf_bytes
    filename = f"fatura-{inv.number:04d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="{filename}"'},
    )
