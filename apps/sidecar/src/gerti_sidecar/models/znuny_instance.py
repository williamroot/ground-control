"""Modelo ZnunyInstance — registra cada instância Znuny gerenciada."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

InstanceMode = Literal["pool", "dedicated"]


class ZnunyInstance(Base):
    __tablename__ = "znuny_instance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    db_dsn_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    webservice_token_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    webhook_signing_secret_ref: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[InstanceMode] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
