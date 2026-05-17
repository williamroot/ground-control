"""Modelo Tenant — um cliente da Gerti."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class Tenant(Base):
    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint("subdomain", name="uq_tenant_subdomain"),
        UniqueConstraint("znuny_customer_id", name="uq_tenant_znuny_customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    trade_name: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[str] = mapped_column(String, nullable=False)
    znuny_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    znuny_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.znuny_instance.id"),
        nullable=False,
    )
    subdomain: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
