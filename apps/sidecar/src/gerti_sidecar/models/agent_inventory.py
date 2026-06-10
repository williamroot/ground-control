"""AgentEnrollToken + DeviceAgent — auto-registro de equipamentos no CMDB (Spec #1R-a).

Tenant-scoped (FORCE RLS por tenant_id, mesmo padrão de csat/automation). As
credenciais NUNCA são persistidas em plaintext: `agent_enroll_token.token_hash`
e `device_agent.agent_secret_hash` guardam só o sha256 hex (comparação
constant-time no domínio; ver domain/agent_secrets.py).

- `AgentEnrollToken`: token de instalação por tenant. `token_hash` UNIQUE (sha256);
  `expires_at`/`max_registrations` (NULL = ilimitado)/`enabled` são as travas
  híbridas anti-token-vazado; `registration_count` é incrementado a cada device
  novo `active`.
- `DeviceAgent`: equipamento registrado. `UNIQUE(tenant_id, fingerprint)` faz o
  dedupe (re-enroll da mesma máquina = atualiza, não duplica). `status`
  pending|active|revoked (CHECK). `znuny_config_item_id` = CI no CMDB (NULL
  enquanto pending). `specs` JSONB (cpu/memory/disco/serial/vendor/model/SO).
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

DEVICE_STATUSES = ("pending", "active", "revoked")


class AgentEnrollToken(Base):
    __tablename__ = "agent_enroll_token"
    __table_args__ = (UniqueConstraint("token_hash", name="ux_agent_enroll_token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    max_registrations: Mapped[int | None] = mapped_column(Integer)
    registration_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class DeviceAgent(Base):
    __tablename__ = "device_agent"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint", name="ux_device_agent_tenant_fingerprint"),
        CheckConstraint("status IN ('pending','active','revoked')", name="ck_device_agent_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    agent_secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    znuny_config_item_id: Mapped[int | None] = mapped_column(Integer)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    os: Mapped[str | None] = mapped_column(String)
    specs: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
