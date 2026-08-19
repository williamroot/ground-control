"""Modelos da agenda de atividades recorrentes (T-R11.1, R11).

Migration 0031. FORCE RLS por tenant_id nas duas tabelas.

`RecurringTaskRun` existe por um motivo só: `UNIQUE(task_id, occurrence_date)`.
É ele que garante que rodar o processador duas vezes no mesmo dia gera **um**
chamado, não dois — a idempotência é do banco, não do código.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

FREQUENCIES = ("once", "weekly", "monthly")


class RecurringTask(Base):
    __tablename__ = "recurring_task"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    weekday: Mapped[int | None] = mapped_column(SmallInteger)
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)
    at_time: Mapped[dt.time] = mapped_column(Time, nullable=False, server_default=text("'08:00'"))
    starts_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[dt.date | None] = mapped_column(Date)
    znuny_queue_name: Mapped[str | None] = mapped_column(Text)
    service: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    customer_user_login: Mapped[str] = mapped_column(Text, nullable=False)
    # Vazio = não consome contrato (suposição S4). Ver a migration 0031.
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RecurringTaskRun(Base):
    __tablename__ = "recurring_task_run"
    __table_args__ = (
        UniqueConstraint("task_id", "occurrence_date", name="uq_recurring_task_run_occurrence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.recurring_task.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurrence_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    znuny_ticket_id: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
