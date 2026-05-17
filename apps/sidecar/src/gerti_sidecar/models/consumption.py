"""ConsumptionEvent (append-only) + Glosa (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import GlosaStatus

_glosa_status = ENUM(GlosaStatus, name="glosa_status", schema="gerti", create_type=False)


class ConsumptionEvent(Base):
    __tablename__ = "consumption_event"

    # H4: BIGSERIAL-equivalent — Identity makes the sequence; plain
    # autoincrement under op.create_table with explicit PK does NOT.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False
    )
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str] = mapped_column(String, nullable=False)
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.service_catalog_item.id")
    )
    billable_minutes: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0"
    )
    billable_amount_brl: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    unit_price_at_event: Mapped[float | None] = mapped_column(Numeric(14, 2))
    # H8: settled-by pointer. UUID, NO ForeignKey (a FK here would create a
    # circular FK with gerti.glosa). Integrity enforced in the app layer.
    glosa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closing_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract_cycle.id")
    )
    recorded_by: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Glosa(Base):
    __tablename__ = "glosa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    consumption_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("gerti.consumption_event.id"), nullable=False
    )
    status: Mapped[GlosaStatus] = mapped_column(
        _glosa_status,
        nullable=False,
        server_default=text("'pending'::gerti.glosa_status"),
    )  # H1
    reason: Mapped[str] = mapped_column(String, nullable=False)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_note: Mapped[str | None] = mapped_column(String)
