"""Modelo TenantQueue — quais filas do Znuny cada cliente acessa (T-R5.1, R5).

Migration 0029. FORCE RLS por tenant_id, igual às irmãs. `znuny_queue_name` é
denormalização declarada (exibir sem ida ao GI); a verdade do nome é o Znuny, e
a gravação valida o id contra a lista viva antes de persistir.

No máximo uma fila padrão por cliente — garantido pelo índice parcial único
`ux_tenant_queue_default`, no banco, não na aplicação.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class TenantQueue(Base):
    __tablename__ = "tenant_queue"
    __table_args__ = (
        UniqueConstraint("tenant_id", "znuny_queue_id", name="uq_tenant_queue_tenant_queue"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    znuny_queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    znuny_queue_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
