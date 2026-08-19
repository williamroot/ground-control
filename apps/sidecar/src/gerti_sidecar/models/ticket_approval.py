"""Aprovação de chamado (R7, Onda 5). Migration 0032.

*"Todo ticket passa, quando essa chave tá habilitada, todo ticket passa por
aqui e vai pra um aprovador. Ele tem acesso ao portal, quando vem um ticket ele
recebe um e-mail pra aprovar, ele entra lá no portal e aprova ou não aprova."*
(07:40)

`UNIQUE(tenant_id, znuny_ticket_id)`: **uma decisão por chamado**. É o que faz
a segunda chamada virar 409 em vez de sobrescrever a primeira em silêncio —
alguém aprovando o que já foi reprovado, sem rastro.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class TicketApproval(Base):
    __tablename__ = "ticket_approval"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_ticket_approval_status"
        ),
        UniqueConstraint("tenant_id", "znuny_ticket_id", name="uq_ticket_approval_tenant_ticket"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id", ondelete="CASCADE"), nullable=False
    )
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    approver_login: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TenantBillingConfig(Base):
    """Configuração de faturamento por cliente (R6, Onda 5).

    *"Aqui eu configuro se manda e-mail, se manda SMS, para quem vai a
    cobrança."* (05:20)

    **Defaults seguros: tudo desligado.** Ligar aviso automático é decisão do
    cliente, não estado herdado de um default nosso — e no SMS isso tem custo
    por mensagem, então um default ligado seria conta na fatura de alguém.
    """

    __tablename__ = "tenant_billing_config"
    __table_args__ = (
        CheckConstraint(
            "billing_day IS NULL OR (billing_day BETWEEN 1 AND 28)",
            name="ck_tenant_billing_config_day",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    billing_email: Mapped[str | None] = mapped_column(Text)
    billing_phone: Mapped[str | None] = mapped_column(Text)
    # Dia do mês em que a cobrança sai. Teto em 28 de propósito: 29-31 não
    # existem em todo mês, e "dia 31" viraria a mesma armadilha da agenda.
    billing_day: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)
