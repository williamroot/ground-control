"""Aprovação de chamados (R7, Onda 5).

*"Tem uma função de autorização de tickets, de aprovação… na DataStone a gente
utiliza, todo ticket passa, quando essa chave tá habilitada, todo ticket passa
por aqui e vai pra um aprovador. Ele tem acesso ao portal, quando vem um ticket
ele recebe um e-mail pra aprovar, ele entra lá no portal e aprova ou não aprova
o ticket."* (07:40)

## Duas decisões que este módulo materializa

**1. O chamado nasce em estado REAL de espera no Znuny — não "criado e
escondido".** Se ele existisse normal e só ficasse invisível no portal, um
agente pegaria e atenderia algo que o cliente ainda não autorizou. O estado é
do tipo `pending`, o que também **para o relógio de SLA**: o cliente que demora
a aprovar não queima o SLA da Gerti. Essa segunda parte não é detalhe — é a
diferença entre um recurso e uma armadilha contratual.

**2. A decisão é única.** `UNIQUE(tenant_id, znuny_ticket_id)` na tabela, e a
segunda chamada devolve **409** em vez de sobrescrever a primeira. Sem isso,
alguém aprovaria o que já foi reprovado, sem rastro.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import TicketApproval
from gerti_sidecar.models.enums import PortalRole
from gerti_sidecar.models.ticket_approval import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
)

# Nome do estado Znuny em que o chamado espera. Criado idempotentemente pelo
# provisionamento (`ensure-approval-state.pl`), do tipo `pending reminder`
# para o relógio de SLA não correr.
PENDING_STATE = "aguardando aprovacao"

# Quem pode decidir. `admin` entra junto de propósito: numa empresa pequena o
# aprovador costuma ser o próprio administrador do portal, e exigir um papel
# separado criaria trabalho de cadastro para nada.
DECIDER_ROLES = (PortalRole.approver, PortalRole.admin)


class ApprovalError(Exception):
    """Base."""


class AlreadyDecided(ApprovalError):
    """Já houve decisão (-> 409)."""


class NotAllowed(ApprovalError):
    """Quem pediu não pode decidir (-> 403)."""


class ApprovalNotFound(ApprovalError):
    """Não existe pendência para este chamado (-> 404)."""


@dataclass(slots=True)
class Decision:
    status: str
    approver_login: str
    reason: str | None


class ApprovalService:
    """Sessão RLS-scoped no tenant. `gi` é o cliente de tickets do Znuny."""

    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self.session = session
        self._gi = gi

    async def open_pending(
        self, *, tenant_id: uuid.UUID, znuny_ticket_id: int, requested_by: str
    ) -> TicketApproval:
        """Registra a pendência. Idempotente: chamado já pendente devolve o mesmo."""
        # SAVEPOINT, não rollback: este método roda DENTRO da transação que
        # abriu o chamado (a mesma que carrega o GUC `app.current_tenant`).
        # Um `rollback()` aqui derrubaria a transação externa junto — foi o
        # que o teste de idempotência pegou. Molde: `invoice_service`, que já
        # trata a colisão de UNIQUE do mesmo jeito.
        sp = await self.session.begin_nested()
        approval = TicketApproval(
            tenant_id=tenant_id,
            znuny_ticket_id=znuny_ticket_id,
            status=STATUS_PENDING,
            requested_by=requested_by,
        )
        try:
            self.session.add(approval)
            await self.session.flush()
        except IntegrityError:
            await sp.rollback()
            existing = await self.get(znuny_ticket_id)
            if existing is None:  # pragma: no cover - corrida improvável
                raise
            return existing
        return approval

    async def get(self, znuny_ticket_id: int) -> TicketApproval | None:
        found: TicketApproval | None = await self.session.scalar(
            select(TicketApproval).where(TicketApproval.znuny_ticket_id == znuny_ticket_id)
        )
        return found

    async def decide(
        self,
        *,
        znuny_ticket_id: int,
        decision: str,
        approver_login: str,
        approver_role: PortalRole,
        reason: str | None = None,
        target_state: str = "open",
    ) -> TicketApproval:
        """Aprova ou reprova. Uma vez só.

        Aprovar move o chamado ao estado normal; reprovar fecha com o motivo
        registrado no próprio chamado — o cliente precisa conseguir ler por que
        o pedido dele não passou, sem depender de alguém contar.
        """
        if decision not in (STATUS_APPROVED, STATUS_REJECTED):
            raise ApprovalError(f"decisão inválida: {decision}")
        if approver_role not in DECIDER_ROLES:
            raise NotAllowed("este usuário não decide aprovação")
        if decision == STATUS_REJECTED and not (reason or "").strip():
            # Reprovar sem motivo deixa o cliente sem saber o que fazer a
            # seguir — e o histórico sem explicação.
            raise ApprovalError("informe o motivo da reprovação")

        approval = await self.get(znuny_ticket_id)
        if approval is None:
            raise ApprovalNotFound(str(znuny_ticket_id))
        if approval.status != STATUS_PENDING:
            raise AlreadyDecided(approval.status)

        # O Znuny primeiro: se a mudança de estado falhar, a decisão não fica
        # gravada dizendo "aprovado" com o chamado parado em espera.
        new_state = target_state if decision == STATUS_APPROVED else "closed unsuccessful"
        note = (
            f"Aprovado por {approver_login}."
            if decision == STATUS_APPROVED
            else f"Reprovado por {approver_login}: {reason}"
        )
        await self._gi.agent_ticket_update(ticket_id=znuny_ticket_id, state=new_state, note=note)

        approval.status = decision
        approval.approver_login = approver_login
        approval.reason = reason
        approval.decided_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return approval

    async def pending_for_tenant(self) -> list[TicketApproval]:
        """A fila de aprovação do portal. RLS já escopa ao tenant da sessão."""
        rows = (
            (
                await self.session.execute(
                    select(TicketApproval)
                    .where(TicketApproval.status == STATUS_PENDING)
                    .order_by(TicketApproval.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)
