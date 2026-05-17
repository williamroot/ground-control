"""TicketContractLink (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import BillingStatus

_billing_status = ENUM(BillingStatus, name="billing_status", schema="gerti", create_type=False)


class TicketContractLink(Base):
    __tablename__ = "ticket_contract_link"

    znuny_ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    billing_status: Mapped[BillingStatus] = mapped_column(
        _billing_status,
        nullable=False,
        server_default=text("'pending'::gerti.billing_status"),  # H1
    )
    linked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    linked_by_rule: Mapped[str] = mapped_column(String, nullable=False)
