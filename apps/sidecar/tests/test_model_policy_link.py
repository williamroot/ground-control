"""ContractAdjustmentRule + ContractRenewalPolicy + TicketContractLink models."""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.models import (
    Contract,
    ContractAdjustmentRule,
    ContractRenewalPolicy,
    TicketContractLink,
)
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_policy_and_ticket_link(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(
        tenant_id=a_id,
        code="C1",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        created_by="s",
    )
    session.add(c)
    await session.flush()
    session.add(
        ContractAdjustmentRule(
            contract_id=c.id,
            index_code="IPCA",
            cadence_months=12,
            next_run_on=dt.date(2027, 1, 1),
        )
    )
    session.add(
        ContractRenewalPolicy(
            contract_id=c.id,
            auto_renew=True,
            notice_days=30,
            next_review_on=dt.date(2026, 11, 1),
        )
    )
    session.add(
        TicketContractLink(
            znuny_ticket_id=12345,
            contract_id=c.id,
            tenant_id=a_id,
            linked_by_rule="auto:default",
        )
    )
    await session.flush()
    link = await session.get(TicketContractLink, 12345)
    assert link is not None
    assert link.contract_id == c.id
    assert link.billing_status == "pending"
