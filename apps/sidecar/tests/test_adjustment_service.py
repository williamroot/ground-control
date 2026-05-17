import datetime as dt

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.adjustment_service import AdjustmentService, _add_months
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.models import ContractAdjustmentRule, ContractRenewalPolicy
from gerti_sidecar.models.enums import ContractStatus, ContractType


def test_add_months_last_day_clamp():
    """S4: month-end anniversaries clamp to the target month's LAST day,
    NOT a flat 28 (billing-date money bug)."""
    # Jan-31 + 1m → Feb 28 (2026 non-leap), NOT Jan-28 wrong-clamp.
    assert _add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    # Leap year: Jan-31 + 1m → Feb 29.
    assert _add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)
    # 31 → April (30 days) → Apr 30.
    assert _add_months(dt.date(2026, 3, 31), 1) == dt.date(2026, 4, 30)
    # Day preserved when valid: Mar-31 + 12m → Mar 31 next year.
    assert _add_months(dt.date(2026, 3, 31), 12) == dt.date(2027, 3, 31)
    # Mid-month unaffected.
    assert _add_months(dt.date(2026, 1, 15), 1) == dt.date(2026, 2, 15)
    # Year rollover.
    assert _add_months(dt.date(2026, 12, 31), 2) == dt.date(2027, 2, 28)


@pytest.mark.asyncio
async def test_apply_index_and_renew(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="C",
                type=ContractType.credit_brl,
                starts_on=dt.date(2025, 1, 1),
                ends_on=dt.date(2026, 1, 1),
                initial_amount_brl=1000,
                unit_price_brl=100,
                created_by="w",
            )
        )
        s.add(
            ContractAdjustmentRule(
                contract_id=c.id,
                index_code="IPCA",
                cadence_months=12,
                next_run_on=dt.date(2026, 1, 1),
            )
        )
        s.add(
            ContractRenewalPolicy(
                contract_id=c.id,
                auto_renew=True,
                notice_days=30,
                next_review_on=dt.date(2025, 12, 1),
                renewal_term_months=12,
            )
        )
        await s.flush()
        adj = AdjustmentService(s)
        new_price = await adj.apply_adjustment(c.id, percent=10.0, on_date=dt.date(2026, 1, 1))
        assert float(new_price) == 110.0  # 100 + 10%
        rule = await s.get(ContractAdjustmentRule, c.id)
        assert rule.last_applied_percent == 10 and rule.next_run_on == dt.date(2027, 1, 1)

        renewed = await adj.renew(c.id, on_date=dt.date(2025, 12, 1))
        assert renewed.ends_on == dt.date(2027, 1, 1)  # +12 months
        assert renewed.status == ContractStatus.active
