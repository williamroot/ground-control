"""Idempotent append-only consumption recording + per-type balance."""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ConsumptionError
from gerti_sidecar.models import ConsumptionEvent, Contract, Glosa
from gerti_sidecar.models.enums import ContractType, GlosaStatus


@dataclasses.dataclass(slots=True)
class RecordConsumption:
    contract_id: uuid.UUID
    occurred_at: dt.datetime
    source_kind: str
    source_ref: str
    billable_minutes: float
    recorded_by: str
    webhook_event_id: uuid.UUID | None = None
    billable_amount_brl: float = 0.0
    service_id: uuid.UUID | None = None


@dataclasses.dataclass(slots=True)
class Balance:
    kind: str  # "hours" | "brl" | "services" | "n/a"
    remaining: float | None


class ConsumptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, data: RecordConsumption) -> ConsumptionEvent:
        if data.billable_minutes < 0:
            raise ConsumptionError("billable_minutes não pode ser negativo")
        if data.webhook_event_id is not None:
            existing = await self.session.execute(
                select(ConsumptionEvent).where(
                    ConsumptionEvent.webhook_event_id == data.webhook_event_id
                )
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                return row  # idempotent: do not double-count
        contract = await self.session.get(Contract, data.contract_id)
        if contract is None:
            raise ConsumptionError("contrato inexistente neste tenant")
        ev = ConsumptionEvent(
            contract_id=data.contract_id,
            occurred_at=data.occurred_at,
            source_kind=data.source_kind,
            source_ref=data.source_ref,
            service_id=data.service_id,
            billable_minutes=data.billable_minutes,
            billable_amount_brl=data.billable_amount_brl,
            unit_price_at_event=contract.unit_price_brl,
            recorded_by=data.recorded_by,
            webhook_event_id=data.webhook_event_id,
        )
        self.session.add(ev)
        await self.session.flush()
        return ev

    async def balance(self, contract_id: uuid.UUID) -> Balance:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ConsumptionError("contrato inexistente neste tenant")
        # S3 GLOSA RULE (single source of truth — see "Domain rules" §):
        # ONLY an APPROVED glosa removes a consumption from the balance.
        # pending & rejected glosas STILL COUNT (money is owed until the
        # write-off is approved). An event is excluded iff its glosa_id
        # points at a glosa whose status = 'approved'.
        approved_glosa_ids = (
            select(Glosa.id).where(Glosa.status == GlosaStatus.approved).scalar_subquery()
        )
        # NOTE the explicit `glosa_id IS NULL` arm: SQL `NULL NOT IN (..)` is
        # NULL (would WRONGLY drop un-glosa'd events). Events with no glosa,
        # or a pending/rejected glosa, MUST count.
        not_written_off = sa.or_(
            ConsumptionEvent.glosa_id.is_(None),
            ConsumptionEvent.glosa_id.not_in(approved_glosa_ids),
        )
        consumed_min = await self.session.scalar(
            select(func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0)).where(
                ConsumptionEvent.contract_id == contract_id,
                not_written_off,
            )
        )
        consumed_brl = await self.session.scalar(
            select(func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)).where(
                ConsumptionEvent.contract_id == contract_id,
                not_written_off,
            )
        )
        consumed_count = await self.session.scalar(
            select(func.count()).where(
                ConsumptionEvent.contract_id == contract_id,
                not_written_off,
                ConsumptionEvent.source_kind == "service_item",
            )
        )
        if contract.type == ContractType.hour_bank:
            initial = float(contract.initial_hours or 0)
            return Balance("hours", initial - float(consumed_min or 0) / 60.0)
        if contract.type in (ContractType.credit_brl, ContractType.credit_shared):
            initial = float(contract.initial_amount_brl or 0)
            return Balance("brl", initial - float(consumed_brl or 0))
        if contract.type == ContractType.service_count:
            initial = float(contract.initial_service_count or 0)
            return Balance("services", initial - float(consumed_count or 0))
        return Balance("n/a", None)  # closed_value / saas_product: no running balance
