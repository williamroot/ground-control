"""Invoice + InvoiceLine — fatura interna não-fiscal (Spec #1P).

Tenant-scoped (FORCE RLS). `invoice_line.tenant_id` é denormalizado para uma
policy RLS direta + índice (evita subselect via invoice). Numeração sequencial
por tenant (UNIQUE tenant_id, number). PDF persistido como bytea na própria
linha (transacional, sem coordenação de volume).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import InvoiceStatus

# H1: native enum defaults MUST be explicitly cast to the gerti.* type.
_invoice_status = ENUM(InvoiceStatus, name="invoice_status", schema="gerti", create_type=False)


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_invoice_tenant_id_number"),
        UniqueConstraint("cycle_id", name="uq_invoice_cycle_id"),
        CheckConstraint("total_cents >= 0", name="ck_invoice_total_cents_non_negative"),
        CheckConstraint("subtotal_cents >= 0", name="ck_invoice_subtotal_cents_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False
    )
    # 1 fatura por ciclo (idempotência). cycle_id pode ser NULL (fatura avulsa).
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract_cycle.id")
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        _invoice_status,
        nullable=False,
        server_default=text("'open'::gerti.invoice_status"),  # H1
    )
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    due_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="BRL")
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    pdf_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    pdf_generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),  # H10: advance on any ORM-mediated mutation
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalizado p/ policy RLS direta + índice (evita subselect via invoice).
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    unit: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
