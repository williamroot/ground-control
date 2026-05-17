"""ContractCycle + ConsumptionEvent (append-only) + Glosa: model, idempotency,
append-only trigger and per-tenant RLS isolation."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gerti_sidecar import db
from gerti_sidecar.models import ConsumptionEvent, Contract, ContractCycle, Glosa
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus, GlosaStatus


@pytest.mark.asyncio
async def test_cycle_consumption_glosa(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = Contract(
        tenant_id=a_id,
        code="C1",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        unit_price_brl=180,
        created_by="s",
    )
    session.add(c)
    await session.flush()
    cyc = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 3, 31),
    )
    session.add(cyc)
    await session.flush()
    assert cyc.status == CycleStatus.open

    ev = ConsumptionEvent(
        contract_id=c.id,
        occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
        source_kind="ticket_work",
        source_ref="znuny:article:1",
        billable_minutes=30,
        billable_amount_brl=0,
        recorded_by="tec",
        webhook_event_id="11111111-1111-1111-1111-111111111111",
    )
    session.add(ev)
    await session.flush()

    # idempotency: same webhook_event_id rejected by the partial unique index
    dup = ConsumptionEvent(
        contract_id=c.id,
        occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
        source_kind="ticket_work",
        source_ref="znuny:article:1",
        billable_minutes=30,
        billable_amount_brl=0,
        recorded_by="tec",
        webhook_event_id="11111111-1111-1111-1111-111111111111",
    )
    # Savepoint so the rejected dup is undone without discarding `ev`
    # (the `session` fixture is one transaction; a bare rollback would
    # also drop the original event and break the FK below).
    sp = await session.begin_nested()
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()

    g = Glosa(consumption_event_id=ev.id, reason="fora do escopo", requested_by="cliente")
    session.add(g)
    await session.flush()
    assert g.status == GlosaStatus.pending


@pytest.mark.asyncio
async def test_consumption_event_append_only(session, seed_two_tenants):
    """H2: DELETE always blocked; UPDATE of a ledger column blocked; an
    UPDATE that touches only closing_cycle_id is allowed."""
    a_id, _ = seed_two_tenants
    c = Contract(
        tenant_id=a_id,
        code="C2",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        unit_price_brl=180,
        created_by="s",
    )
    session.add(c)
    await session.flush()
    cyc = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 3, 31),
    )
    session.add(cyc)
    await session.flush()
    ev = ConsumptionEvent(
        contract_id=c.id,
        occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
        source_kind="ticket_work",
        source_ref="znuny:article:9",
        billable_minutes=30,
        billable_amount_brl=0,
        recorded_by="tec",
    )
    session.add(ev)
    await session.flush()
    ev_id = ev.id

    # DELETE → always forbidden (savepoint-scoped so `ev` survives).
    with pytest.raises(Exception):  # noqa: B017 (plpgsql RAISE EXCEPTION)
        async with session.begin_nested():
            await session.execute(
                text("DELETE FROM gerti.consumption_event WHERE id = :i"), {"i": ev_id}
            )

    # UPDATE of a ledger (immutable) column → forbidden
    with pytest.raises(Exception):  # noqa: B017 (plpgsql RAISE EXCEPTION)
        async with session.begin_nested():
            await session.execute(
                text("UPDATE gerti.consumption_event SET billable_minutes = 999 WHERE id = :i"),
                {"i": ev_id},
            )

    # UPDATE touching only closing_cycle_id → allowed (CycleService.close())
    await session.execute(
        text("UPDATE gerti.consumption_event SET closing_cycle_id = :c WHERE id = :i"),
        {"c": cyc.id, "i": ev_id},
    )
    row = (
        await session.execute(
            text("SELECT closing_cycle_id FROM gerti.consumption_event WHERE id = :i"),
            {"i": ev_id},
        )
    ).scalar_one()
    assert row == cyc.id


@pytest.mark.asyncio
async def test_cycle_consumption_glosa_rls(session, app_session_factory, seed_two_tenants):
    """Per-tenant RLS via the owning contract: tenant A sees only its own
    cycle/consumption/glosa; tenant B sees none; unset GUC sees zero rows."""
    a_id, b_id = seed_two_tenants

    async def _seed(tenant_id, code):
        c = Contract(
            tenant_id=tenant_id,
            code=code,
            type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_hours=40,
            unit_price_brl=180,
            created_by="s",
        )
        session.add(c)
        await session.flush()
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 3, 31),
        )
        session.add(cyc)
        await session.flush()
        ev = ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 1, 5, 14, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"znuny:{code}",
            billable_minutes=15,
            billable_amount_brl=0,
            recorded_by="tec",
        )
        session.add(ev)
        await session.flush()
        g = Glosa(consumption_event_id=ev.id, reason=code, requested_by="cli")
        session.add(g)
        await session.flush()

    await _seed(a_id, "A")
    await _seed(b_id, "B")
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        cycles = (await s.execute(text("SELECT count(*) FROM gerti.contract_cycle"))).scalar_one()
        events = (
            (await s.execute(text("SELECT source_ref FROM gerti.consumption_event")))
            .scalars()
            .all()
        )
        glosas = (await s.execute(text("SELECT reason FROM gerti.glosa"))).scalars().all()
    assert cycles == 1
    assert events == ["znuny:A"]
    assert glosas == ["A"]

    # tenant B → only its own
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        events = (
            (await s.execute(text("SELECT source_ref FROM gerti.consumption_event")))
            .scalars()
            .all()
        )
        glosas = (await s.execute(text("SELECT reason FROM gerti.glosa"))).scalars().all()
    assert events == ["znuny:B"]
    assert glosas == ["B"]

    # unset GUC → fail-closed (zero rows on all three)
    async with app_session_factory() as s:
        assert (
            await s.execute(text("SELECT count(*) FROM gerti.contract_cycle"))
        ).scalar_one() == 0
        assert (
            await s.execute(text("SELECT count(*) FROM gerti.consumption_event"))
        ).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM gerti.glosa"))).scalar_one() == 0
