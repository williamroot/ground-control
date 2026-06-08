"""Reconcilia time_accounting do Znuny → gerti.consumption_event (Spec #1B).

Leitura cross-tenant (AdminSessionLocal/BYPASSRLS) de vínculos+contratos+cursor;
escrita por-tenant (tenant_session_scope, RLS-subject) via ConsumptionService.
Idempotência determinística por uuid5 sobre o id do lançamento. O débito de saldo
é automático (balance() soma por tipo). closed_value/saas/service_count recebem o
evento mas o balance() não os afeta por tempo.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.models import (
    ConsumptionSyncCursor,
    Contract,
    TicketContractLink,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType

# Namespace fixo p/ derivar webhook_event_id determinístico do id do lançamento.
NS_TIMEACCOUNTING = uuid.UUID("6f1d2b1e-0000-4b1b-9b1b-7e57acc00000")

_CREDIT_TYPES = (ContractType.credit_brl, ContractType.credit_shared)


def _time_unit_to_minutes() -> float:
    raw = os.environ.get("TIME_UNIT_TO_MINUTES", "1")
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _parse_dt(s: str) -> dt.datetime:
    # Znuny create_time: 'YYYY-MM-DD HH:MM:SS' (sem tz) → assume UTC.
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC)
    except (ValueError, TypeError):
        return dt.datetime.now(dt.UTC)


class ReconciliationService:
    def __init__(self, gi: Any) -> None:
        self._gi = gi  # módulo/obj com time_accounting_since(since_id, limit)

    async def reconcile(self, *, limit: int = 500) -> int:
        """Puxa lançamentos novos e grava consumption_events. Retorna nº gravado."""
        if db.AdminSessionLocal is None:
            raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")

        # 1) cursor (admin/BYPASSRLS). MVP: um único znuny_instance.
        async with db.AdminSessionLocal() as admin:
            inst_id = await admin.scalar(select(ZnunyInstance.id).limit(1))
            if inst_id is None:
                return 0
            cursor = await admin.get(ConsumptionSyncCursor, inst_id)
            since_id = cursor.last_time_accounting_id if cursor is not None else 0

        # 2) pull
        page = await self._gi.time_accounting_since(since_id=since_id, limit=limit)
        if not page.entries:
            return 0

        # 3) leitura cross-tenant: ticket -> (contract, tenant)
        ticket_ids = {e.ticket_id for e in page.entries}
        async with db.AdminSessionLocal() as admin:
            links = (
                await admin.execute(
                    select(TicketContractLink).where(
                        TicketContractLink.znuny_ticket_id.in_(ticket_ids)
                    )
                )
            ).scalars().all()
            link_by_ticket: dict[int, TicketContractLink] = {
                lnk.znuny_ticket_id: lnk for lnk in links
            }
            contract_ids = {lnk.contract_id for lnk in links}
            contracts = (
                await admin.execute(select(Contract).where(Contract.id.in_(contract_ids)))
            ).scalars().all()
            contract_by_id: dict[uuid.UUID, Contract] = {c.id: c for c in contracts}

        factor = _time_unit_to_minutes()

        # 4) agrupar por tenant e gravar (RLS-subject)
        by_tenant: dict[uuid.UUID, list[tuple[Any, TicketContractLink]]] = defaultdict(list)
        for e in page.entries:
            lnk = link_by_ticket.get(e.ticket_id)
            if lnk is None:
                # Cursor avança mesmo sobre entradas sem vínculo; um ticket linkado APÓS
                # o scan do seu lançamento perderia aquele tempo. Isso é seguro porque
                # #1E vincula tickets na criação (antes de qualquer lançamento).
                continue  # ticket sem contrato → ignora
            by_tenant[lnk.tenant_id].append((e, lnk))

        written = 0
        for tenant_id, items in by_tenant.items():
            async with db.tenant_session_scope(tenant_id) as s:
                svc = ConsumptionService(s)
                for e, lnk in items:
                    contract = contract_by_id.get(lnk.contract_id)
                    if contract is None:
                        continue
                    minutes = float(e.time_unit) * factor
                    amount = 0.0
                    if contract.type in _CREDIT_TYPES:
                        price = float(contract.unit_price_brl or 0)
                        amount = round((minutes / 60.0) * price, 2)
                    ref = (
                        f"znuny:article:{e.article_id}"
                        if e.article_id
                        else f"znuny:ticket:{e.ticket_id}"
                    )
                    event_id = uuid.uuid5(
                        NS_TIMEACCOUNTING, f"znuny:timeaccounting:{e.id}"
                    )
                    await svc.record(
                        RecordConsumption(
                            contract_id=lnk.contract_id,
                            occurred_at=_parse_dt(e.created),
                            source_kind="ticket_work",
                            source_ref=ref,
                            billable_minutes=minutes,
                            recorded_by="worker:reconcile",
                            billable_amount_brl=amount,
                            webhook_event_id=event_id,
                        )
                    )
                    written += 1

        # 5) avança cursor (admin/BYPASSRLS) p/ o MaxId puxado
        async with db.AdminSessionLocal() as admin:
            cursor = await admin.get(ConsumptionSyncCursor, inst_id)
            if cursor is None:
                cursor = ConsumptionSyncCursor(
                    znuny_instance_id=inst_id,
                    last_time_accounting_id=page.max_id,
                )
                admin.add(cursor)
            else:
                cursor.last_time_accounting_id = page.max_id
                cursor.updated_at = dt.datetime.now(dt.UTC)
            await admin.commit()

        return written
