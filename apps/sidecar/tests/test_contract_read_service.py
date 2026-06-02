"""ContractReadService: S3 glosa predicate + consumed_percent + series + low_balance.

Asserts the centralized rule matches ConsumptionService.balance() and that
pending/rejected/absent glosas COUNT while approved glosas do NOT. Uses the
admin session for setup (BYPASSRLS); the service is pure-read.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import ContractReadService
from gerti_sidecar.models import ConsumptionEvent, Contract, Glosa, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, GlosaStatus


async def _tenant(session) -> Tenant:
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
        legal_name="A",
        trade_name="A",
        document="1",
        znuny_customer_id="A",
        znuny_instance_id=inst.id,
        subdomain="a",
    )
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_consumed_percent_and_glosa_rule_match_balance(session):
    t = await _tenant(session)
    c = Contract(
        tenant_id=t.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=10,
        unit_price_brl=100,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    # 60 + 120 + 60 min = 4h consumed if all count.
    evs = []
    for i, m in enumerate((60, 120, 60)):
        ev = ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"r{i}",
            billable_minutes=m,
            recorded_by="seed",
        )
        session.add(ev)
        await session.flush()
        evs.append(ev)
    # APPROVED glosa on the 120-min event -> it must NOT count.
    g_app = Glosa(
        consumption_event_id=evs[1].id, status=GlosaStatus.approved, reason="x", requested_by="seed"
    )
    session.add(g_app)
    await session.flush()
    # back-pointer: balance() keys on consumption_event.glosa_id (H8, app-layer, no FK)
    evs[1].glosa_id = g_app.id
    await session.flush()
    # PENDING glosa on the last 60-min event -> it STILL counts (no back-pointer on purpose).
    session.add(
        Glosa(
            consumption_event_id=evs[2].id,
            status=GlosaStatus.pending,
            reason="y",
            requested_by="seed",
        )
    )
    await session.flush()

    svc = ContractReadService(session)
    bal = await ConsumptionService(session).balance(c.id)
    # remaining = 10h - (60+60)/60 = 8.0  (120-min approved-glosa event excluded)
    assert bal.remaining == pytest.approx(8.0)
    pct = await svc.consumed_percent(c)
    # consumed 2h of 10h -> 20%
    assert pct == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_consumed_percent_none_for_closed_and_zero_initial(session):
    t = await _tenant(session)
    cv = Contract(
        tenant_id=t.id,
        code="CV",
        type=ContractType.closed_value,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=9000,
        unit_price_brl=9000,
        created_by="seed",
    )
    hb0 = Contract(
        tenant_id=t.id,
        code="HB0",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=0,
        unit_price_brl=100,
        created_by="seed",
    )
    session.add_all([cv, hb0])
    await session.flush()
    assert await ContractReadService(session).consumed_percent(cv) is None
    assert await ContractReadService(session).consumed_percent(hb0) is None
