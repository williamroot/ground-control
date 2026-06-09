"""CsatService (Spec #1M): grava a avaliação CSAT 1-5 do cliente por ticket.

Guardas (server-side, fail-closed):
  - posse + existência: via GI get_ticket(znuny_ticket_id, customer_id) — já
    customer-scoped (ZnunyWriteError p/ não-encontrado/posse → CsatError);
  - estado: só fechado ('closed' no nome do estado) senão TicketNotClosed (422);
  - 1 resposta por ticket: UNIQUE (tenant_id, znuny_ticket_id) → IntegrityError
    capturado como CsatAlreadyExists (409);
  - score 1-5 (CsatError p/ fora do range); comment truncado a 2000 chars.

Opera sob sessão tenant-scoped (RLS): o caller abre tenant_session_scope.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import (
    CsatAlreadyExists,
    CsatError,
    TicketNotClosed,
)
from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError
from gerti_sidecar.models.csat import CsatResponse

__all__ = [
    "CsatAlreadyExists",
    "CsatError",
    "CsatService",
    "TicketNotClosed",
]

_MAX_COMMENT = 2000


class CsatService:
    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self._session = session
        self._gi = gi

    async def find(self, *, tenant_id: uuid.UUID, znuny_ticket_id: int) -> CsatResponse | None:
        return (
            await self._session.execute(
                select(CsatResponse).where(
                    CsatResponse.tenant_id == tenant_id,
                    CsatResponse.znuny_ticket_id == znuny_ticket_id,
                )
            )
        ).scalar_one_or_none()

    async def submit(
        self,
        *,
        tenant_id: uuid.UUID,
        znuny_ticket_id: int,
        customer_login: str,
        customer_id: str,
        score: int,
        comment: str | None,
    ) -> CsatResponse:
        if score < 1 or score > 5:
            raise CsatError("score fora do range 1..5")

        # Posse + existência: o GI é customer-scoped; não-encontrado/posse → 404.
        try:
            ticket = await self._gi.get_ticket(
                znuny_ticket_id=znuny_ticket_id, customer_id=customer_id
            )
        except ZnunyWriteError as exc:
            raise CsatError("ticket_not_found") from exc

        state = (getattr(ticket, "state", None) or "").lower()
        if "closed" not in state:
            raise TicketNotClosed("ticket não está fechado")

        clean_comment = comment.strip()[:_MAX_COMMENT] if comment else None

        row = CsatResponse(
            tenant_id=tenant_id,
            znuny_ticket_id=znuny_ticket_id,
            customer_login=customer_login,
            score=score,
            comment=clean_comment,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise CsatAlreadyExists("csat já existe para este ticket") from exc
        return row
