"""ServiceCatalogItem + SharedCreditPool (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import CycleKind

_cycle_kind = ENUM(CycleKind, name="cycle_kind", schema="gerti", create_type=False)


class ServiceCatalogItem(Base):
    __tablename__ = "service_catalog_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id")
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    default_queue_name: Mapped[str] = mapped_column(String, nullable=False)
    default_priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="3")
    default_sla_minutes: Mapped[int | None] = mapped_column(Integer)
    form_schema: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )  # H1-class
    unit_price_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SharedCreditPool(Base):
    __tablename__ = "shared_credit_pool"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    total_amount_brl: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cycle_kind: Mapped[CycleKind] = mapped_column(_cycle_kind, nullable=False)
    cycle_period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    current_cycle_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
