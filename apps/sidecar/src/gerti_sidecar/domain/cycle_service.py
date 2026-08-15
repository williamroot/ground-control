"""Close a closing-cycle: compute consumption, overage, accrual, glosa, snapshot.

Franquia efetiva (`hour_bank`): `initial_hours * 60` **mais** o saldo não usado do
ciclo de fechamento anterior quando o contrato tem "Acumular saldo entre ciclos"
(`contract.accumulate_balance_between_cycles`). Sem isso o `carry_over` era
gravado e nunca lido — e a franquia do mês seguinte voltava ao valor cheio,
cobrando excedente que o cliente não tinha (a fatura só passou a expor esse erro
quando `hour_bank` deixou de sair R$ 0,00, T-R15.4).

O acúmulo é em **cadeia**: o `carry_over` do ciclo N já embute o de N-1, porque
entra na franquia efetiva que gera o carry de N. Hoje é **sem teto e sem
expiração** — se o negócio exigir cap/validade, é regra de dinheiro e precisa de
decisão explícita antes de mudar.
"""

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

        is_hour_bank = contract.type == ContractType.hour_bank
        base_franchise_minutes = float(contract.initial_hours or 0) * 60.0 if is_hour_bank else 0.0
        carry_in_minutes = await self._carry_in_minutes(contract, cycle) if is_hour_bank else 0.0
        franchise_minutes = base_franchise_minutes + carry_in_minutes
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
            # franchise_minutes é a franquia EFETIVA do ciclo (base + acúmulo).
            "base_franchise_minutes": base_franchise_minutes,
            "carry_in_minutes": carry_in_minutes,
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

    async def _carry_in_minutes(self, contract: Contract, cycle: ContractCycle) -> float:
        """Saldo de franquia herdado do ciclo de fechamento anterior (minutos).

        Zero quando o contrato não acumula, quando este é o primeiro ciclo, ou
        quando o ciclo anterior não tem `totals` (fechado por versão antiga).
        Só considera ciclos de fechamento JÁ encerrados (`closed`/`invoiced`)
        que terminaram antes do início deste — o mais recente deles.
        """
        if not contract.accumulate_balance_between_cycles:
            return 0.0
        previous = (
            await self.session.execute(
                select(ContractCycle)
                .where(
                    ContractCycle.contract_id == contract.id,
                    ContractCycle.kind == CycleKind.closing,
                    ContractCycle.status != CycleStatus.open,
                    ContractCycle.id != cycle.id,
                    ContractCycle.period_end < cycle.period_start,
                )
                .order_by(ContractCycle.period_end.desc(), ContractCycle.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if previous is None or not previous.totals:
            return 0.0
        raw = previous.totals.get("carry_over")
        if not isinstance(raw, int | float):
            return 0.0
        return max(0.0, float(raw))
