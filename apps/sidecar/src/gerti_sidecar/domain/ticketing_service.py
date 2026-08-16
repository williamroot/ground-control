"""Domínio de abertura de chamado (Spec #1E).

Regra de seleção de contrato (D-1E-2): 0 informado + 1 ativo => auto; 0 + >=2 =>
ContractChoiceRequired (422); informado e inexistente/ inativo sob RLS =>
NoActiveContract (404). Grava gerti.ticket_contract_link DEPOIS de o ticket
nascer no Znuny (billing-ready para a #1B).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import Contract, TenantQueue, TicketContractLink
from gerti_sidecar.models.enums import ContractStatus


class NoActiveContract(Exception):
    """Contrato informado não existe / não está ativo sob o tenant (->404)."""


class ContractChoiceRequired(Exception):
    """Há >=2 contratos ativos e nenhum foi escolhido (->422)."""


class QueueNotAllowed(Exception):
    """Fila informada não está associada a este cliente (->422)."""


@dataclass(frozen=True)
class OpenTicketInput:
    customer_user: str
    customer_id: str
    title: str
    body: str
    service: str | None
    type_: str | None
    priority: str | None
    contract_id: str | None
    attachments: list[Any]
    config_item_id: int | None = None
    queue: str | None = None


@dataclass(frozen=True)
class OpenedTicket:
    znuny_ticket_id: int
    ticket_number: str
    contract_id: str


class TicketingService:
    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self._session = session
        self._gi = gi

    async def _active_contract_ids(self) -> list[uuid.UUID]:
        # RLS já filtra por tenant (app.current_tenant via tenant_session_scope).
        rows = await self._session.execute(
            select(Contract.id).where(Contract.status == ContractStatus.active)
        )
        return [r[0] for r in rows.all()]

    async def _resolve_contract(self, requested: str | None) -> uuid.UUID:
        active = await self._active_contract_ids()
        if requested is not None:
            try:
                rid = uuid.UUID(requested)
            except ValueError as exc:
                raise NoActiveContract("contrato inválido") from exc
            if rid not in active:
                raise NoActiveContract("contrato não encontrado ou inativo")
            return rid
        if len(active) == 1:
            return active[0]
        if len(active) == 0:
            raise NoActiveContract("nenhum contrato ativo para abrir chamado")
        raise ContractChoiceRequired("selecione um contrato")

    async def _resolve_queue(self, requested: str | None) -> str | None:
        """Fila em que o chamado nasce (T-R5.3).

        Antes desta onda o destino era a string `'Raw'`, fixa em
        `TicketCreate.pm:67`: todo chamado de todo cliente caía no mesmo lugar,
        e não havia como configurar. Agora:

          • fila informada  → precisa estar associada a este cliente, senão 422
          • nada informado  → a fila padrão do cliente
          • cliente sem configuração → None, e o Perl mantém o `Raw` histórico

        RLS já escopa `tenant_queue` ao tenant da sessão; não há como enxergar
        nem cair na fila de outro cliente por id.
        """
        result = await self._session.execute(
            select(TenantQueue.znuny_queue_name, TenantQueue.is_default)
        )
        rows = result.all()
        if requested is not None:
            allowed = {name for name, _ in rows}
            if requested not in allowed:
                raise QueueNotAllowed(f"fila {requested!r} não está associada a este cliente")
            return requested
        for name, is_default in rows:
            if is_default:
                return str(name)
        return None

    async def open_ticket(self, data: OpenTicketInput) -> OpenedTicket:
        contract_id = await self._resolve_contract(data.contract_id)
        queue = await self._resolve_queue(data.queue)

        created = await self._gi.create_ticket(
            customer_user=data.customer_user,
            customer_id=data.customer_id,
            title=data.title,
            body=data.body,
            service=data.service,
            type_=data.type_,
            priority=data.priority,
            contract_id=str(contract_id),
            attachments=data.attachments or None,
            config_item_id=data.config_item_id,
            queue=queue,
        )

        # tenant_id vem do GUC app.current_tenant; a FK + RLS garantem o escopo.
        tenant_row = await self._session.execute(
            select(Contract.tenant_id).where(Contract.id == contract_id)
        )
        tenant_id = tenant_row.scalar_one()
        self._session.add(
            TicketContractLink(
                znuny_ticket_id=created.znuny_ticket_id,
                contract_id=contract_id,
                tenant_id=tenant_id,
                linked_by_rule=f"portal:{data.customer_user}",
            )
        )
        await self._session.flush()
        return OpenedTicket(created.znuny_ticket_id, created.ticket_number, str(contract_id))
