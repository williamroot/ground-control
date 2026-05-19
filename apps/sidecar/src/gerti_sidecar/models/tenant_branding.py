"""Modelo TenantBranding — white-label 1:1 com o tenant."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class TenantBranding(Base):
    __tablename__ = "tenant_branding"
    __table_args__ = (
        CheckConstraint("default_theme IN ('light','dark')", name="ck_tenant_branding_theme"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String)
    primary_color: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'#2563EB'")
    )
    accent_color: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'#1E40AF'")
    )
    default_theme: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'light'")
    )
    support_email: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
