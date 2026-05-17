"""Index adjustment (reajuste) + automatic renewal."""

from __future__ import annotations

import calendar
import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import Contract, ContractAdjustmentRule, ContractRenewalPolicy


def _add_months(d: dt.date, months: int) -> dt.date:
    """Add `months` calendar months, preserving the day-of-month when the
    target month has it, else clamping to that month's LAST day.

    S4 — billing-date money bug fix: a naive `min(day, 28)` would move a
    Jan-31 anniversary to the 28th of every month (losing 2-3 days of
    billing period and silently shifting every subsequent cycle). Correct
    semantics: keep the original day when valid (e.g. 31→Mar 31), otherwise
    use the actual last day of the target month (31→Feb 28/29, →Apr 30).
    """
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    last_day = calendar.monthrange(year, month)[1]  # 28/29/30/31
    day = d.day if d.day <= last_day else last_day
    return dt.date(year, month, day)


class AdjustmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def apply_adjustment(
        self, contract_id: uuid.UUID, *, percent: float, on_date: dt.date
    ) -> float:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ContractValidationError("contrato inexistente neste tenant")
        rule = await self.session.get(ContractAdjustmentRule, contract_id)
        if rule is None:
            raise ContractValidationError("contrato sem regra de reajuste")
        if rule.cap_percent is not None and percent > float(rule.cap_percent):
            percent = float(rule.cap_percent)  # honor the cap
        base = float(contract.unit_price_brl or 0)
        new_price = round(base * (1 + percent / 100.0), 2)
        contract.unit_price_brl = new_price
        rule.last_applied_on = on_date
        rule.last_applied_percent = percent
        rule.next_run_on = _add_months(on_date, rule.cadence_months)
        await self.session.flush()
        return new_price

    async def renew(self, contract_id: uuid.UUID, *, on_date: dt.date) -> Contract:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise ContractValidationError("contrato inexistente neste tenant")
        policy = await self.session.get(ContractRenewalPolicy, contract_id)
        if policy is None or not policy.auto_renew:
            raise ContractValidationError("contrato sem renovação automática")
        term = policy.renewal_term_months or 12
        contract.ends_on = _add_months(contract.ends_on, term)
        contract.status = contract.status.__class__.active
        policy.next_review_on = _add_months(on_date, term)
        await self.session.flush()
        return contract
