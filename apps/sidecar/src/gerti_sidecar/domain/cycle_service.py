"""Close a closing-cycle: compute consumption, overage, accrual, glosa, snapshot."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import CycleError
from gerti_sidecar.models import ConsumptionEvent, Contract, ContractCycle, Glosa
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus, GlosaStatus


class CycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def close(self, cycle_id: uuid.UUID) -> dict[str, object]:
        cycle = await self.session.get(ContractCycle, cycle_id)
        if cycle is None:
            raise CycleError("ciclo inexistente neste tenant")
        if cycle.kind != CycleKind.closing:
            raise CycleError("apenas ciclos de fechamento podem ser fechados")
        if cycle.status != CycleStatus.open:
            raise CycleError(f"ciclo não está aberto (status={cycle.status})")
        contract = await self.session.get(Contract, cycle.contract_id)
        if contract is None:
            raise CycleError("contrato do ciclo inexistente")

        start = dt.datetime.combine(cycle.period_start, dt.time.min, tzinfo=dt.UTC)
        end = dt.datetime.combine(cycle.period_end, dt.time.max, tzinfo=dt.UTC)

        # Events in window, not yet assigned a closing cycle, and not
        # written-off by an APPROVED glosa (pending/rejected still count).
        approved_sub = (
            select(Glosa.consumption_event_id)
            .where(Glosa.status == GlosaStatus.approved)
            .scalar_subquery()
        )
        rows = (
            (
                await self.session.execute(
                    select(ConsumptionEvent).where(
                        ConsumptionEvent.contract_id == contract.id,
                        ConsumptionEvent.closing_cycle_id.is_(None),
                        ConsumptionEvent.occurred_at >= start,
                        ConsumptionEvent.occurred_at <= end,
                        ConsumptionEvent.id.not_in(approved_sub),
                    )
                )
            )
            .scalars()
            .all()
        )

        consumed_minutes = sum(float(r.billable_minutes) for r in rows)
        consumed_brl = sum(float(r.billable_amount_brl) for r in rows)

        franchise_minutes = (
            float(contract.initial_hours or 0) * 60.0
            if contract.type == ContractType.hour_bank
            else 0.0
        )
        overage_minutes = max(0.0, consumed_minutes - franchise_minutes)
        unit = float(contract.unit_price_brl or 0)
        overage_amount = (
            (overage_minutes / 60.0) * unit if contract.type == ContractType.hour_bank else 0.0
        )

        if contract.accumulate_balance_between_cycles:
            carry_over = max(0.0, franchise_minutes - consumed_minutes)
        else:
            carry_over = 0.0

        totals: dict[str, object] = {
            "consumed_minutes": consumed_minutes,
            "consumed_brl": consumed_brl,
            "franchise_minutes": franchise_minutes,
            "overage_minutes": overage_minutes,
            "overage_amount_brl": overage_amount,
            "carry_over": carry_over,
            "event_count": len(rows),
        }

        await self.session.execute(
            update(ConsumptionEvent)
            .where(ConsumptionEvent.id.in_([r.id for r in rows]))
            .values(closing_cycle_id=cycle.id)
        )
        cycle.status = CycleStatus.closed
        cycle.closed_at = dt.datetime.now(dt.UTC)  # H5: Python value, not func.now()
        cycle.totals = totals
        await self.session.flush()
        return totals
