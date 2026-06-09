"""AiGenerationLog — auditoria/custo de geração de IA (Spec #1N).

Tabela OPERACIONAL, cross-tenant, SEM RLS (mesmo padrão de agent_timer): cada
sumarização/resposta sugerida registra uma linha (agente, ticket, tipo, modelo,
duração, sucesso). Lida/gravada via AdminSessionLocal (BYPASSRLS). Não contém
o conteúdo do ticket nem a saída do LLM — só metadados de auditoria.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class AiGenerationLog(Base):
    __tablename__ = "ai_generation_log"
    __table_args__ = (
        CheckConstraint("kind IN ('summary','reply')", name="ck_ai_generation_log_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_login: Mapped[str] = mapped_column(String, nullable=False)
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # summary | reply
    model: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
