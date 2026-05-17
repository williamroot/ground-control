import datetime as dt
import uuid

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


@pytest.mark.asyncio
async def test_close_cycle_overage_and_accrual(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="HB",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=2,
                unit_price_brl=150,
                billing_period_months=1,
                closing_period_months=1,
                accumulate_balance_between_cycles=False,
                created_by="w",
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
        await cons.record(
            RecordConsumption(
                contract_id=c.id,
                occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="a:1",
                billable_minutes=180,
                recorded_by="t",
                webhook_event_id=uuid.uuid4(),
            )
        )
        totals = await CycleService(s).close(cyc.id)
        # consumed 3h, franchise/initial 2h → 1h overage * 150 = 150
        assert totals["consumed_minutes"] == 180
        assert totals["overage_minutes"] == 60
        assert float(totals["overage_amount_brl"]) == 150.0
        assert totals["carry_over"] == 0  # accrual disabled
        refreshed = await s.get(ContractCycle, cyc.id)
        assert refreshed.status == CycleStatus.closed and refreshed.closed_at is not None
        # consumption events stamped with this closing cycle
        from sqlalchemy import func, select

        from gerti_sidecar.models import ConsumptionEvent

        n = await s.scalar(select(func.count()).where(ConsumptionEvent.closing_cycle_id == cyc.id))
        assert n == 1
