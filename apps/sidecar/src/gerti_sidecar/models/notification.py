"""Notification — central de notificações do cliente (Spec #3 V3).

Tenant-scoped (FORCE RLS). A policy RLS só isola por tenant; o escopo por
destinatário (`recipient_login` == login da sessão) é responsabilidade da
camada de serviço/router — dois usuários do mesmo tenant nunca enxergam a
notificação um do outro (ver domain/notification_service.py e
routers/notifications.py). Emissão via `NotificationService.emit`,
idempotente por (tenant_id, recipient_login, kind, link_path, dia).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

# Kinds válidos — String + CheckConstraint em vez de enum nativo (H1: evita
# CREATE TYPE e o footgun de cast do default).
NOTIFICATION_KINDS = (
    "ticket_update",
    "ticket_reply",
    "sla_warning",
    "sla_breach",
    "contract_alert",
    "invoice_issued",
    "system",
)


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in NOTIFICATION_KINDS) + ")",
            name="ck_notification_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    recipient_login: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String)
    link_path: Mapped[str | None] = mapped_column(String)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
