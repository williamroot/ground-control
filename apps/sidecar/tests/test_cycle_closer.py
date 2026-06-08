from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.domain.cycle_closer import CycleCloser
from gerti_sidecar.models import Contract, ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


@pytest.mark.asyncio
async def test_closes_only_due_open_closing_cycles(
    engine, app_session_factory, session, monkeypatch
):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Acme",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    c = Contract(
        tenant_id=t.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    due = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
        status=CycleStatus.open,
    )
    future = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2099, 1, 1),
        period_end=dt.date(2099, 1, 31),
        status=CycleStatus.open,
    )
    session.add_all([due, future])
    await session.commit()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    closed = await CycleCloser().close_due_cycles(today=dt.date(2026, 6, 8))
    assert closed == 1  # só o vencido

    async with db.AdminSessionLocal() as a:
        d = await a.get(ContractCycle, due.id)
        f = await a.get(ContractCycle, future.id)
        assert d.status == CycleStatus.closed
        assert f.status == CycleStatus.open

    # idempotente
    assert await CycleCloser().close_due_cycles(today=dt.date(2026, 6, 8)) == 0
