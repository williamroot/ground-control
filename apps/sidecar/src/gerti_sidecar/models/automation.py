"""AutomationRule + AutomationRun — motor de automação próprio (Spec #1Q).

Tenant-scoped (FORCE RLS por tenant_id, mesmo padrão das demais tabelas de
negócio). Uma `automation_rule` é uma regra no-code: gatilho de evento +
condições (lista JSONB `[{field, op, value}]`, AND) + ações (lista JSONB
`[{type, params}]`, allowlist). `automation_run` é o registro append-only de
cada avaliação de regra contra um evento de ticket (auditoria).

CHECK em `trigger_event` espelha a allowlist do domínio
(`ticket_create|article_create|state_update|escalation`).
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
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

TRIGGER_EVENTS = ("ticket_create", "article_create", "state_update", "escalation")


class AutomationRule(Base):
    __tablename__ = "automation_rule"
    __table_args__ = (
        CheckConstraint(
            "trigger_event IN ('ticket_create','article_create','state_update','escalation')",
            name="ck_automation_rule_trigger_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    trigger_event: Mapped[str] = mapped_column(String, nullable=False)
    conditions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    actions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AutomationRun(Base):
    __tablename__ = "automation_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.automation_rule.id"), nullable=False
    )
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actions_result: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
