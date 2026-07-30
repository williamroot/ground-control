"""CatalogItem — Catálogo de Serviços do portal (Spec #3 V2).

**Nota de nomenclatura:** o contrato da Spec #3 reserva o nome de tabela
`service_catalog_item`, mas esse nome já existe (`gerti.service_catalog_item`,
Spec #0 §4 — tabela de billing/consumo referenciada por FK em
`contract_scope`/`consumption`, ver `models/catalog.py`). Por instrução do
plano ("se algo aqui divergir do código existente, o código existente
vence"), esta tabela usa o nome `catalog_item` para não colidir.

Tenant-scoped (FORCE RLS). Cliente enxerga só `active=true`; console vê tudo.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

ALLOWED_ICONS = (
    "ticket",
    "shield",
    "user-plus",
    "server",
    "package",
    "database",
    "box",
    "printer",
    "lock",
    "wifi",
    "mail",
    "settings",
)


class CatalogItem(Base):
    __tablename__ = "catalog_item"
    __table_args__ = (
        CheckConstraint(
            "icon IN ('ticket', 'shield', 'user-plus', 'server', 'package', 'database', "
            "'box', 'printer', 'lock', 'wifi', 'mail', 'settings')",
            name="ck_catalog_item_icon",
        ),
        CheckConstraint(
            "sla_hours IS NULL OR sla_hours BETWEEN 1 AND 720", name="ck_catalog_item_sla_hours"
        ),
        CheckConstraint("sort_order BETWEEN 0 AND 999", name="ck_catalog_item_sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    icon: Mapped[str] = mapped_column(String, nullable=False, server_default="ticket")
    znuny_queue: Mapped[str | None] = mapped_column(String)
    znuny_service: Mapped[str | None] = mapped_column(String)
    default_priority: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
