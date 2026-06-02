"""Modelo PortalUserRole — papel (admin/helpdesk) por usuário, escopado ao tenant (Spec #1H).

`customer_login` casa com o claim `customer_login` do JWT (o e-mail/identificador
de login). A unicidade real (tenant_id, lower(customer_login)) é garantida por
índice funcional na migration 0012. FORCE RLS por tenant_id (igual às demais gerti.*).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import PortalRole

# create_type=False: o tipo gerti.portal_role é criado pela migration 0012 (H1).
_portal_role = ENUM(PortalRole, name="portal_role", schema="gerti", create_type=False)


class PortalUserRole(Base):
    __tablename__ = "portal_user_role"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_login: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[PortalRole] = mapped_column(_portal_role, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
