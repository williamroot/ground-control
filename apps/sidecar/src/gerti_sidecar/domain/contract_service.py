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


# Which "initial_*" field each type requires.
_REQUIRED: dict[ContractType, str] = {
    ContractType.credit_brl: "initial_amount_brl",
    ContractType.credit_shared: "initial_amount_brl",
    ContractType.hour_bank: "initial_hours",
    ContractType.service_count: "initial_service_count",
    ContractType.closed_value: "initial_amount_brl",
    ContractType.saas_product: "initial_amount_brl",
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: NewContract) -> Contract:
        if data.ends_on <= data.starts_on:
            raise ContractValidationError("ends_on deve ser > starts_on")
        if data.billing_period_months < 1 or data.closing_period_months < 1:
            raise ContractValidationError("períodos devem ser >= 1 mês")
        if (
            data.closing_period_months % data.billing_period_months != 0
            and data.billing_period_months % data.closing_period_months != 0
        ):
            raise ContractValidationError("ciclos de faturamento e fechamento devem ser múltiplos")
        required = _REQUIRED[data.type]
        if getattr(data, required) in (None, 0):
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
