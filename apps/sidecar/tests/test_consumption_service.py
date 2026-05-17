import datetime as dt
import uuid

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_record_idempotent_and_balance(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        contract = await ContractService(s).create(
            NewContract(
                code="HB",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=10,
                unit_price_brl=200,
                created_by="w",
            )
        )
        cons = ConsumptionService(s)
        wid = uuid.uuid4()
        ev1 = await cons.record(
            RecordConsumption(
                contract_id=contract.id,
                occurred_at=dt.datetime(2026, 1, 5, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="znuny:article:1",
                billable_minutes=120,
                recorded_by="tec",
                webhook_event_id=wid,
            )
        )
        ev2 = await cons.record(
            RecordConsumption(
                contract_id=contract.id,
                occurred_at=dt.datetime(2026, 1, 5, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="znuny:article:1",
                billable_minutes=120,
                recorded_by="tec",
                webhook_event_id=wid,
            )
        )
        assert ev1.id == ev2.id  # idempotent: same webhook id → same row
        bal = await cons.balance(contract.id)
        # hour_bank: 10h - 120min(2h) = 8h remaining
        assert bal.kind == "hours" and float(bal.remaining) == 8.0
