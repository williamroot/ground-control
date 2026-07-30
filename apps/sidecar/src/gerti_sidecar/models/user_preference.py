"""UserPreference — preferências do usuário no Portal (tema, alertas) (Spec #3 V3).

Tenant-scoped (FORCE RLS). UNIQUE (tenant_id, user_login): 1 linha por login
por tenant. Criada sob demanda (upsert idempotente) por
`domain/preference_service.py::get_or_create` na primeira leitura.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

# String + CheckConstraint em vez de enum nativo (H1).
THEME_VALUES = ("light", "dark", "system")


class UserPreference(Base):
    __tablename__ = "user_preference"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_login", name="uq_user_preference_tenant_id_user_login"),
        CheckConstraint("theme IN ('light','dark','system')", name="ck_user_preference_theme"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    user_login: Mapped[str] = mapped_column(String, nullable=False)
    theme: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'system'"))
    email_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sla_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ticket_updates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    contract_alerts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    invoice_alerts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    weekly_report: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
