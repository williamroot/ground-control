"""CsatResponse — avaliação CSAT 1-5 do cliente por ticket (Spec #1M).

Tenant-scoped (FORCE RLS por tenant_id), 1 resposta por (tenant_id, ticket).
A média alimenta o dashboard (#1O) que lê desta tabela.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class CsatResponse(Base):
    __tablename__ = "csat_response"
    __table_args__ = (
        UniqueConstraint("tenant_id", "znuny_ticket_id", name="ux_csat_ticket"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_csat_response_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_login: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
