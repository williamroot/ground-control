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

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.models import (
    ConsumptionOrphan,
    ConsumptionSyncCursor,
    Contract,
    Tenant,
    TicketContractLink,
    ZnunyInstance,
)
from gerti_sidecar.models.consumption_orphan import (
    REASON_AMBIGUOUS_CONTRACT,
    REASON_NO_ACTIVE_CONTRACT,
    REASON_NO_TENANT,
)
from gerti_sidecar.models.enums import ContractStatus, ContractType

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

    async def _link_orphans(self, orphans: list[Any]) -> dict[int, TicketContractLink]:
        """Vincula (ou registra a pendência de) lançamentos sem contrato — T-R2.3.

        Um chamado por e-mail nasce sem `ticket_contract_link`: o vínculo só é
        criado no `POST /v1/tickets` do portal. Sem esta etapa, a hora lançada
        nele é descartada em silêncio pelo passo 4.

        Resolução, por chamado:
          • CustomerID não casa com nenhum tenant → pendência `no_tenant`
          • tenant com exatamente 1 contrato ativo → **vincula** e a hora entra
          • 0 contratos ativos  → pendência `no_active_contract`
          • ≥2 contratos ativos → pendência `ambiguous_contract` (precisa de
            humano: escolher por conta própria seria faturar no contrato errado)

        Devolve os vínculos criados, por ticket.
        """
        if db.AdminSessionLocal is None:  # pragma: no cover - guarda de sanidade
            return {}

        # Um chamado pode ter vários lançamentos na mesma página; resolvemos o
        # chamado uma vez só, e a pendência é por LANÇAMENTO (é o lançamento que
        # se perde, não o chamado).
        customer_by_ticket: dict[int, str] = {}
        for e in orphans:
            cid = (getattr(e, "customer_id", "") or "").strip()
            if cid and e.ticket_id not in customer_by_ticket:
                customer_by_ticket[e.ticket_id] = cid

        async with db.AdminSessionLocal() as admin:
            wanted = {c.lower() for c in customer_by_ticket.values()}
            tenant_by_customer: dict[str, uuid.UUID] = {}
            if wanted:
                rows = (
                    await admin.execute(
                        select(Tenant.id, Tenant.znuny_customer_id).where(
                            func.lower(Tenant.znuny_customer_id).in_(wanted)
                        )
                    )
                ).all()
                tenant_by_customer = {str(cid).lower(): tid for tid, cid in rows}

            # Contratos ativos por tenant, numa consulta só.
            tenant_ids = set(tenant_by_customer.values())
            active_by_tenant: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
            if tenant_ids:
                for tid, cid in (
                    await admin.execute(
                        select(Contract.tenant_id, Contract.id).where(
                            Contract.tenant_id.in_(tenant_ids),
                            Contract.status == ContractStatus.active,
                        )
                    )
                ).all():
                    active_by_tenant[tid].append(cid)

        resolved: dict[int, TicketContractLink] = {}
        decided: dict[int, tuple[str, uuid.UUID | None]] = {}  # ticket -> (reason|"ok", tenant)
        for ticket_id in {e.ticket_id for e in orphans}:
            customer_id = customer_by_ticket.get(ticket_id, "")
            tenant_id = tenant_by_customer.get(customer_id.lower()) if customer_id else None
            if tenant_id is None:
                decided[ticket_id] = (REASON_NO_TENANT, None)
                continue
            active = active_by_tenant.get(tenant_id, [])
            if len(active) == 1:
                decided[ticket_id] = ("ok", tenant_id)
            elif not active:
                decided[ticket_id] = (REASON_NO_ACTIVE_CONTRACT, tenant_id)
            else:
                decided[ticket_id] = (REASON_AMBIGUOUS_CONTRACT, tenant_id)

        # Vínculos: escrita RLS-subject, por tenant (nunca pela sessão admin).
        for ticket_id, (verdict, tenant_id) in decided.items():
            if verdict != "ok" or tenant_id is None:
                continue
            contract_id = active_by_tenant[tenant_id][0]
            fields = {
                "znuny_ticket_id": ticket_id,
                "contract_id": contract_id,
                "tenant_id": tenant_id,
                "linked_by_rule": "worker:auto-link:single-active-contract",
            }
            async with db.tenant_session_scope(tenant_id) as s:
                s.add(TicketContractLink(**fields))
            # Cópia transiente para o passo 4: a instância acima morre com a
            # sessão, e o que interessa adiante são só contract_id/tenant_id.
            resolved[ticket_id] = TicketContractLink(**fields)

        # Pendências: uma linha por LANÇAMENTO não atribuído, idempotente por id.
        pending = [
            e for e in orphans if decided.get(e.ticket_id, (REASON_NO_TENANT, None))[0] != "ok"
        ]
        if pending:
            async with db.AdminSessionLocal() as admin:
                for e in pending:
                    reason, tenant_id = decided[e.ticket_id]
                    await admin.execute(
                        pg_insert(ConsumptionOrphan)
                        .values(
                            znuny_time_accounting_id=e.id,
                            znuny_ticket_id=e.ticket_id,
                            znuny_customer_id=(getattr(e, "customer_id", "") or None),
                            tenant_id=tenant_id,
                            time_unit=e.time_unit,
                            occurred_at=_parse_dt(e.created),
                            reason=reason,
                        )
                        .on_conflict_do_nothing(constraint="uq_consumption_orphan_ta")
                    )
                await admin.commit()

        return resolved

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
                (
                    await admin.execute(
                        select(TicketContractLink).where(
                            TicketContractLink.znuny_ticket_id.in_(ticket_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            link_by_ticket: dict[int, TicketContractLink] = {
                lnk.znuny_ticket_id: lnk for lnk in links
            }

        # 3b) lançamento em ticket SEM vínculo (T-R2.3) — o caso de todo chamado
        #     que entra por e-mail. Antes desta onda ele era descartado em
        #     silêncio e o cursor avançava por cima: hora trabalhada sumia sem
        #     erro e sem aviso. Agora tentamos vincular; o que não der, fica
        #     registrado como pendência reprocessável.
        orphans = [e for e in page.entries if e.ticket_id not in link_by_ticket]
        if orphans:
            link_by_ticket.update(await self._link_orphans(orphans))

        # 3c) contratos — DEPOIS do 3b, senão os vínculos recém-criados ficariam
        #     sem contrato carregado e o passo 4 os descartaria de novo, agora
        #     com o vínculo gravado (o pior dos dois mundos).
        async with db.AdminSessionLocal() as admin:
            contract_ids = {lnk.contract_id for lnk in link_by_ticket.values()}
            contracts = (
                (await admin.execute(select(Contract).where(Contract.id.in_(contract_ids))))
                .scalars()
                .all()
            )
            contract_by_id: dict[uuid.UUID, Contract] = {c.id: c for c in contracts}

        factor = _time_unit_to_minutes()

        # 4) agrupar por tenant e gravar (RLS-subject)
        by_tenant: dict[uuid.UUID, list[tuple[Any, TicketContractLink]]] = defaultdict(list)
        for e in page.entries:
            lnk = link_by_ticket.get(e.ticket_id)
            if lnk is None:
                # Cursor avança mesmo sobre entradas sem vínculo (decisão D-E:
                # não mexer no avanço, que é código financeiro vivo). O descarte
                # deixou de ser silencioso — 3b já registrou a pendência.
                continue
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
                    event_id = uuid.uuid5(NS_TIMEACCOUNTING, f"znuny:timeaccounting:{e.id}")
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
