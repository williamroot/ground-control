import datetime as dt

import pytest

from gerti_sidecar.models import Contract, ContractBillingParty
from gerti_sidecar.models.enums import ContractStatus, ContractType


@pytest.mark.asyncio
async def test_create_contract_and_billing_party(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(
        tenant_id=a_id,
        code="CTR-2026-0001",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        unit_price_brl=180,
        billing_period_months=1,
        closing_period_months=3,
        created_by="william",
    )
    session.add(c)
    await session.flush()
    assert c.id is not None
    assert c.status == ContractStatus.active
    assert c.accumulate_balance_between_cycles is False

    bp = ContractBillingParty(
        contract_id=c.id,
        legal_name="A SA",
        document="1",
        fiscal_address={"city": "São Paulo", "uf": "SP"},
    )
    session.add(bp)
    await session.flush()
    assert bp.contract_id == c.id
