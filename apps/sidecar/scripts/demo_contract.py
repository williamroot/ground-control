"""Domain demo: prints a full MSP contract lifecycle. No HTTP, no Znuny.

Run (needs a Postgres reachable + migrations applied):
  cd apps/sidecar
  DATABASE_URL=postgresql+asyncpg://gerti_sidecar:dev_change_me@<host>:5432/gerti \
    uv run python scripts/demo_contract.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind


async def main() -> None:
    admin_url = os.environ["DATABASE_URL"]  # gerti_sidecar works for app ops
    engine = create_async_engine(admin_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # NOTE: tenant seeding requires an admin (BYPASSRLS) connection in real
    # runs; for the demo assume a tenant already exists or seed via psql.
    # Here we just demonstrate the domain services under a tenant GUC.
    tenant_id = uuid.UUID(os.environ["DEMO_TENANT_ID"])

    async with db.tenant_session_scope(tenant_id, factory=factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code=f"DEMO-{uuid.uuid4().hex[:6]}",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=8,
                unit_price_brl=180,
                billing_period_months=1,
                closing_period_months=1,
                created_by="demo",
            )
        )
        print(f"Contrato criado: {c.code} ({c.type}) saldo inicial 8h")
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
        )
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        for mins in (120, 240, 180):
            await cons.record(
                RecordConsumption(
                    contract_id=c.id,
                    occurred_at=dt.datetime(2026, 1, 9, tzinfo=dt.UTC),
                    source_kind="ticket_work",
                    source_ref="demo",
                    billable_minutes=mins,
                    recorded_by="tec",
                    webhook_event_id=uuid.uuid4(),
                )
            )
        bal = await cons.balance(c.id)
        print(f"Após 9h apontadas → saldo {bal.remaining:.1f}h ({bal.kind})")
        totals = await CycleService(s).close(cyc.id)
        print(
            f"Ciclo fechado: excedente {totals['overage_minutes'] / 60:.1f}h "
            f"= R$ {float(totals['overage_amount_brl']):.2f}"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
