"""Modelo ConsumptionOrphan — hora que o worker não atribuiu a contrato (T-R2.3).

Migration 0030. Operacional cross-tenant: **sem RLS** (o `tenant_id` é
justamente o que pode faltar), acessado só por `AdminSessionLocal` (BYPASSRLS).

Existe para que o descarte deixe de ser silencioso: o cursor continua avançando
(decisão D-E — não mexer em código financeiro vivo), mas cada lançamento não
atribuível fica registrado e reprocessável em vez de sumir.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

# Motivos possíveis — espelham o CHECK da migration 0030.
REASON_NO_TENANT = "no_tenant"
REASON_NO_ACTIVE_CONTRACT = "no_active_contract"
REASON_AMBIGUOUS_CONTRACT = "ambiguous_contract"


class ConsumptionOrphan(Base):
    __tablename__ = "consumption_orphan"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('no_tenant','no_active_contract','ambiguous_contract')",
            name="ck_consumption_orphan_reason",
        ),
        CheckConstraint("status IN ('pending','resolved')", name="ck_consumption_orphan_status"),
        UniqueConstraint("znuny_time_accounting_id", name="uq_consumption_orphan_ta"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    znuny_time_accounting_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    znuny_customer_id: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    time_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
