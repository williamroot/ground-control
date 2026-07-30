"""AuditLog — trilha de auditoria operacional (Spec #3 V5).

Tabela OPERACIONAL, cross-tenant, SEM RLS (mesmo padrão de agent_timer/
ai_generation_log/consumption_sync_cursor): cada escrita administrativa
relevante (onboarding, contrato, fatura, branding, tokens de agente, regras
de automação, KB, catálogo) grava uma linha via `domain/audit_service.record`.
Lida/gravada só via `AdminSessionLocal` (BYPASSRLS) — nunca por `gerti_app`.

NUNCA contém segredo, senha, token ou corpo de ticket em `description`/
`metadata` — só metadados de auditoria (ver `domain/audit_service.py`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('agent','customer','system')", name="ck_audit_log_actor_type"
        ),
        CheckConstraint(
            "action IN ('create','update','delete','login','export')", name="ck_audit_log_action"
        ),
        Index("ix_audit_log_at", "at"),
        Index("ix_audit_log_tenant_id_at", "tenant_id", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_login: Mapped[str | None] = mapped_column(String)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(String)
    # Atributo Python != nome da coluna: `metadata` colide com Base.metadata (SQLAlchemy).
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
