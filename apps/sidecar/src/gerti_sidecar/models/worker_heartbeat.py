"""WorkerHeartbeat — prova de vida do worker de consumo (Spec #3).

Tabela OPERACIONAL, cross-tenant, SEM RLS (mesmo padrão de audit_log/
consumption_sync_cursor). Gravada a cada tick do worker (`jobs/worker.py`),
com trabalho ou sem, sucesso ou falha — é o que diferencia "ocioso" de
"travado" na sonda de saúde. Lida/gravada só via `AdminSessionLocal`
(BYPASSRLS) — nunca por `gerti_app`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"

    worker: Mapped[str] = mapped_column(Text, primary_key=True)
    last_tick_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ticks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
