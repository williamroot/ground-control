"""Create/validate contracts honoring the 6 MSP contract types (Spec #0 §4)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractType


@dataclasses.dataclass(slots=True)
class NewContract:
    code: str
    type: ContractType
    starts_on: dt.date
    ends_on: dt.date
    created_by: str
    initial_amount_brl: float | None = None
    initial_hours: float | None = None
    initial_service_count: int | None = None
    unit_price_brl: float | None = None
    travel_franchise_count: int = 0
    billing_period_months: int = 1
    closing_period_months: int = 1
    billing_in_advance: bool = True
    accumulate_balance_between_cycles: bool = False
    # D-Q (Onda 5): o valor contratado é mensal ('month', padrão) ou por
    # fechamento ('cycle')? Muda quantas vezes a mensalidade entra num ciclo
    # trimestral.
    billing_amount_period: str = "month"
    # D-R (Onda 5): teto e validade do saldo acumulado. None = ilimitado, que
    # é o comportamento de antes desta onda.
    carry_over_cap_minutes: float | None = None
    carry_over_cap_amount_brl: float | None = None
    carry_over_expires_days: int | None = None


# Which "initial_*" field each type requires.
_REQUIRED: dict[ContractType, str] = {
    ContractType.credit_brl: "initial_amount_brl",
    ContractType.credit_shared: "initial_amount_brl",
    ContractType.hour_bank: "initial_hours",
    ContractType.service_count: "initial_service_count",
    ContractType.closed_value: "initial_amount_brl",
    ContractType.saas_product: "initial_amount_brl",
    # `free` NÃO aparece aqui de propósito — ver o comentário em `create`.
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: NewContract) -> Contract:
        if data.ends_on <= data.starts_on:
            raise ContractValidationError("ends_on deve ser > starts_on")
        if data.billing_period_months < 1 or data.closing_period_months < 1:
            raise ContractValidationError("períodos devem ser >= 1 mês")
        if data.billing_amount_period not in ("month", "cycle"):
            # O CHECK do banco recusaria de qualquer jeito, mas com erro de
            # driver; aqui a mensagem diz o que fazer.
            raise ContractValidationError(
                "billing_amount_period deve ser 'month' (valor mensal) ou 'cycle' "
                "(valor por fechamento)"
            )
        if data.carry_over_expires_days is not None and data.carry_over_expires_days < 0:
            raise ContractValidationError("a validade do saldo não pode ser negativa")
        if (
            data.closing_period_months % data.billing_period_months != 0
            and data.billing_period_months % data.closing_period_months != 0
        ):
            raise ContractValidationError("ciclos de faturamento e fechamento devem ser múltiplos")
        # D-D / T-R15.2 — o tipo `free` é o único sem campo obrigatório.
        #
        # Ele existe para atender o "cliente avulso, sem contrato" (R15) SEM
        # afrouxar a invariante do #1C de que todo chamado tem contrato: em vez
        # de permitir consumo órfão, o cliente ganha um contrato livre, sem
        # franquia e sem mensalidade, em que tudo o que for feito é cobrado
        # como lançamento avulso. `_REQUIRED.get` em vez de `_REQUIRED[...]`:
        # a indexação direta levantaria KeyError → 500 no primeiro contrato
        # livre criado.
        required = _REQUIRED.get(data.type)
        if required is not None and getattr(data, required) in (None, 0):
            raise ContractValidationError(f"contrato {data.type} exige {required}")
        # tenant uniqueness of code (RLS already scopes the SELECT to tenant)
        dup = await self.session.execute(select(Contract.id).where(Contract.code == data.code))
        if dup.first() is not None:
            raise ContractValidationError(f"código {data.code} já existe neste tenant")

        tenant_id = await self._current_tenant_id()
        contract = Contract(
            tenant_id=tenant_id,
            code=data.code,
            type=data.type,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            initial_amount_brl=data.initial_amount_brl,
            initial_hours=data.initial_hours,
            initial_service_count=data.initial_service_count,
            unit_price_brl=data.unit_price_brl,
            travel_franchise_count=data.travel_franchise_count,
            billing_period_months=data.billing_period_months,
            closing_period_months=data.closing_period_months,
            billing_in_advance=data.billing_in_advance,
            accumulate_balance_between_cycles=data.accumulate_balance_between_cycles,
            billing_amount_period=data.billing_amount_period,
            carry_over_cap_minutes=data.carry_over_cap_minutes,
            carry_over_cap_amount_brl=data.carry_over_cap_amount_brl,
            carry_over_expires_days=data.carry_over_expires_days,
            created_by=data.created_by,
        )
        self.session.add(contract)
        await self.session.flush()
        return contract

    async def _current_tenant_id(self) -> uuid.UUID:
        # H9: imports hoisted to module top (ruff PLC0415-safe).
        res = await self.session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        val = res.scalar_one()
        if not val:
            raise ContractValidationError("sessão sem tenant (GUC ausente)")
        return uuid.UUID(val)
