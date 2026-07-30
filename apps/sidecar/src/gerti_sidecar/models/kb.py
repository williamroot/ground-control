"""KbArticle — Base de Conhecimento (Spec #3 V1).

Tenant-scoped (FORCE RLS). Cliente enxerga só `visibility='public' AND
status='published'`; console (via AdminSessionLocal/BYPASSRLS) vê tudo,
inclusive `draft`/`internal`. Slug é gerado uma única vez na criação
(`kb_service._slugify`) e NUNCA muda no update — preserva links externos.
`views` incrementa via `UPDATE ... SET views = views + 1` (sem race) e nunca
é tocado pelo console.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class KbArticle(Base):
    __tablename__ = "kb_article"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_kb_article_tenant_id_slug"),
        CheckConstraint("visibility IN ('public', 'internal')", name="ck_kb_article_visibility"),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')", name="ck_kb_article_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(String)
    body_markdown: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    visibility: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    author_login: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
