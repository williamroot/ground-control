"""Close a closing-cycle: compute consumption, overage, accrual, glosa, snapshot.

Franquia efetiva (`hour_bank`): `initial_hours * 60` **mais** o saldo não usado do
ciclo de fechamento anterior quando o contrato tem "Acumular saldo entre ciclos"
(`contract.accumulate_balance_between_cycles`). Sem isso o `carry_over` era
gravado e nunca lido — e a franquia do mês seguinte voltava ao valor cheio,
cobrando excedente que o cliente não tinha (a fatura só passou a expor esse erro
quando `hour_bank` deixou de sair R$ 0,00, T-R15.4).

O acúmulo é em **cadeia**: o `carry_over` do ciclo N já embute o de N-1, porque
entra na franquia efetiva que gera o carry de N. **Desde a Onda 5 (decisão D-R)
ele tem teto e validade opcionais**, e por isso o saldo virou uma lista de
baldes datados em `totals["carry_buckets"]` — a cadeia apagava a data de origem,
e sem data de origem "vale 60 dias" não tem como ser aplicado. A regra inteira
está em `domain/carry_over.py`, testada isolada. NULO nas três colunas
(`carry_over_cap_minutes`, `carry_over_cap_amount_brl`, `carry_over_expires_days`)
= ilimitado, que é o padrão e o comportamento de antes.

**`service_count` fecha de verdade a partir da Onda 5 (T-R3.3).** Antes, o tipo
não tinha franquia, nem excedente, nem consumo contado: fechar o ciclo de um
contrato por pacote de atendimentos gerava snapshot vazio e fatura R$ 0,00. A
unidade aqui é o **chamado**, não o apontamento de hora — ver
`ConsumptionService.balance`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain import carry_over
from gerti_sidecar.domain.errors import CycleError
from gerti_sidecar.models import ConsumptionEvent, Contract, ContractCycle, Glosa
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus, GlosaStatus


def _service_units(rows: list[ConsumptionEvent]) -> int:
    """Quantos ATENDIMENTOS os eventos representam (T-R3.3).

    Chamado distinto conta uma vez, por mais apontamentos que tenha.
    Lançamento avulso (deslocamento, despesa) **não** consome o pacote: ele já
    é cobrado à parte, e descontar um atendimento junto cobraria duas vezes
    pela mesma coisa. Mesma regra de `ConsumptionService.balance`.
    """
    return len({r.znuny_ticket_id for r in rows if r.znuny_ticket_id is not None})


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
        is_service_count = contract.type == ContractType.service_count
        unit = float(contract.unit_price_brl or 0)

        # A unidade do acúmulo muda com o tipo do contrato: minutos no banco de
        # horas, atendimentos no pacote. O motor é o mesmo (`carry_over`), só a
        # grandeza e o teto é que trocam.
        if is_hour_bank:
            base_franchise = float(contract.initial_hours or 0) * 60.0
            consumed_units = consumed_minutes
            cap = _as_float(contract.carry_over_cap_minutes)
        elif is_service_count:
            base_franchise = float(contract.initial_service_count or 0)
            consumed_units = float(_service_units(list(rows)))
            cap = None  # teto em atendimentos não foi pedido; ver D-R.
        else:
            base_franchise = 0.0
            consumed_units = 0.0
            cap = None

        carried = carry_over.roll(
            previous=await self._previous_buckets(contract, cycle),
            consumed=consumed_units,
            base_franchise=base_franchise,
            period_start=cycle.period_start,
            period_end=cycle.period_end,
            accumulate=bool(contract.accumulate_balance_between_cycles)
            and (is_hour_bank or is_service_count),
            cap=cap,
            expires_days=contract.carry_over_expires_days,
        )
        franchise = base_franchise + carried.carry_in
        overage_units = max(0.0, consumed_units - franchise)

        if is_hour_bank:
            overage_amount = (overage_units / 60.0) * unit
        elif is_service_count:
            # Atendimento excedente é cobrado pelo preço unitário do contrato.
            # Sem preço configurado o excedente aparece com quantidade e R$ 0,00
            # — visível na fatura, e não cobrado, que é melhor do que inventar
            # um valor.
            overage_amount = overage_units * unit
        else:
            overage_amount = 0.0

        totals: dict[str, object] = {
            "consumed_minutes": consumed_minutes,
            "consumed_brl": consumed_brl,
            # franchise_minutes é a franquia EFETIVA do ciclo (base + acúmulo).
            # Nos contratos por atendimento estas três chaves ficam zeradas e as
            # de `service` é que valem — a fatura escolhe pelo tipo do contrato.
            "base_franchise_minutes": base_franchise if is_hour_bank else 0.0,
            "carry_in_minutes": carried.carry_in if is_hour_bank else 0.0,
            "franchise_minutes": franchise if is_hour_bank else 0.0,
            "overage_minutes": overage_units if is_hour_bank else 0.0,
            "overage_amount_brl": overage_amount,
            "carry_over": carried.carry_out,
            # D-R: os baldes datados, e o que sumiu por prazo/teto. Saldo que
            # desaparece sem alguém poder ver por quê é discussão com o cliente
            # sem resposta.
            "carry_buckets": [b.to_json() for b in carried.buckets_out],
            "carry_expired": carried.expired,
            "carry_capped": carried.capped,
            "event_count": len(rows),
        }
        if is_service_count:
            totals.update(
                {
                    "consumed_services": consumed_units,
                    "base_franchise_services": base_franchise,
                    "carry_in_services": carried.carry_in,
                    "franchise_services": franchise,
                    "overage_services": overage_units,
                }
            )

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

    async def _previous_buckets(
        self, contract: Contract, cycle: ContractCycle
    ) -> list[carry_over.Bucket]:
        """Saldo herdado do ciclo de fechamento anterior, em baldes datados.

        Vazio quando o contrato não acumula, quando este é o primeiro ciclo, ou
        quando o anterior não tem `totals`. Ciclo fechado ANTES da Onda 5 tem
        só o número `carry_over` — ele é convertido num balde datado no fim
        daquele ciclo, senão ligar a validade apagaria o saldo histórico de
        todos os clientes de uma vez.
        """
        if not contract.accumulate_balance_between_cycles:
            return []
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
        if previous is None:
            return []
        return carry_over.buckets_from_cycle_totals(
            previous.totals,
            legacy_key="carry_over",
            fallback_date=previous.period_end,
        )


def _as_float(value: object) -> float | None:
    """Numeric do SQLAlchemy chega como Decimal; None continua None."""
    return None if value is None else float(value)  # type: ignore[arg-type]
