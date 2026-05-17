"""Full lifecycle under RLS as the unprivileged role: create→consume→close→adjust."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.adjustment_service import AdjustmentService
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import Contract, ContractAdjustmentRule, ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind


@pytest.mark.asyncio
async def test_full_contract_lifecycle(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="MSP-OURO",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=4,
                unit_price_brl=160,
                billing_period_months=1,
                closing_period_months=1,
                created_by="william",
            )
        )
        s.add(
            ContractAdjustmentRule(
                contract_id=c.id,
                index_code="IPCA",
                cadence_months=12,
                next_run_on=dt.date(2027, 1, 1),
            )
        )
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
        )
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        for mins in (90, 120, 150):  # 360 min = 6h, franchise 4h → 2h overage
            await cons.record(
                RecordConsumption(
                    contract_id=c.id,
                    occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
                    source_kind="ticket_work",
                    source_ref=f"a:{mins}",
                    billable_minutes=mins,
                    recorded_by="tec",
                    webhook_event_id=uuid.uuid4(),
                )
            )
        bal = await cons.balance(c.id)
        assert bal.kind == "hours" and float(bal.remaining) == -2.0  # 4h - 6h
        totals = await CycleService(s).close(cyc.id)
        assert totals["overage_minutes"] == 120
        assert float(totals["overage_amount_brl"]) == 320.0  # 2h * 160
        new_price = await AdjustmentService(s).apply_adjustment(
            c.id, percent=8.0, on_date=dt.date(2026, 12, 31)
        )
        assert float(new_price) == 172.8  # 160 + 8%

    # tenant B cannot see tenant A's contract at all (RLS, unprivileged role)
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        rows = (await s.execute(select(Contract.code))).scalars().all()
        assert "MSP-OURO" not in rows
