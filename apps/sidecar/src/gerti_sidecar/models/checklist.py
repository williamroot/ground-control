"""R13b — checklists personalizáveis (modelo global + instância por chamado)."""

from __future__ import annotations

import datetime as dt
import uuid

# `text` é importado com apelido porque este módulo tem uma COLUNA chamada
# `text`; sem o apelido, `server_default=sql_text("false")` chamaria o atributo
# mapeado da classe em vez da função do SQLAlchemy.
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ChecklistTemplate(Base):
    """Procedimento da Gerti — não pertence a cliente nenhum, logo sem `tenant_id`."""

    __tablename__ = "checklist_template"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(Text)


class ChecklistTemplateItem(Base):
    __tablename__ = "checklist_template_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.checklist_template.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    text: Mapped[str] = mapped_column(Text, nullable=False)


class TicketChecklist(Base):
    """O modelo aplicado a UM chamado. `UNIQUE(tenant, ticket, template)` = A13.5."""

    __tablename__ = "ticket_checklist"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "znuny_ticket_id",
            "template_id",
            name="uq_ticket_checklist_tenant_ticket_template",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    znuny_ticket_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.checklist_template.id"), nullable=False
    )
    # Nome COPIADO: o modelo pode ser renomeado depois de aplicado.
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied_by: Mapped[str] = mapped_column(Text, nullable=False)


class TicketChecklistItem(Base):
    """Item COPIADO do modelo — editar o modelo não muda o que o técnico marcou."""

    __tablename__ = "ticket_checklist_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    checklist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.ticket_checklist.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    done_by: Mapped[str | None] = mapped_column(Text)
