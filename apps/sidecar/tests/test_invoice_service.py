"""InvoiceService: create_from_cycle idempotente, numeração sequencial, transições.

Seed de contrato + ciclo de fechamento + consumption_events; a fatura agrega as
linhas por source_kind, numera sequencialmente por tenant, e é idempotente por
ciclo (InvoiceAlreadyExists). mark_paid/mark_void aplicam transições; paid/void
são terminais.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.errors import InvoiceAlreadyExists, InvoiceError
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import ContractCycle, Invoice
from gerti_sidecar.models.enums import ContractType, CycleKind, InvoiceStatus


async def _seed_cycle_with_events(s, *, code, events):
    c = await ContractService(s).create(
        NewContract(
            code=code,
            type=ContractType.credit_brl,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_amount_brl=20000,
            unit_price_brl=200,
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
    import uuid

    for i, (kind, minutes, brl) in enumerate(events):
        await cons.record(
            RecordConsumption(
                contract_id=c.id,
                occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
                source_kind=kind,
                source_ref=f"{code}:{i}",
                billable_minutes=minutes,
                billable_amount_brl=brl,
                recorded_by="t",
                webhook_event_id=uuid.uuid4(),
            )
        )
    # Fatura parte de um ciclo fechado (worker #1B fecha; aqui fechamos no seed).
    await CycleService(s).close(cyc.id)
    return c, cyc


@pytest.mark.asyncio
async def test_create_from_cycle_aggregates_and_numbers(
    session, app_session_factory, seed_two_tenants
):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c1, cyc1 = await _seed_cycle_with_events(
            s,
            code="CB1",
            events=[
                ("ticket_work", 60, 200),
                ("ticket_work", 30, 100),
                ("travel", 0, 50),
            ],
        )
        inv = await InvoiceService(s).create_from_cycle(cyc1.id)
        assert inv.status == InvoiceStatus.open
        assert inv.number == 1
        # 2 source_kinds agregados → 2 linhas; total = 200+100+50 = 350 BRL = 35000 cents
        assert inv.total_cents == 35000
        assert inv.subtotal_cents == 35000
        lines = await InvoiceService(s).lines_for(inv.id)
        assert len(lines) == 2
        assert sum(line.amount_cents for line in lines) == 35000

        # segundo ciclo/fatura → number incrementa
        _c2, cyc2 = await _seed_cycle_with_events(s, code="CB2", events=[("ticket_work", 60, 100)])
        inv2 = await InvoiceService(s).create_from_cycle(cyc2.id)
        assert inv2.number == 2


@pytest.mark.asyncio
async def test_create_from_cycle_idempotent(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_cycle_with_events(s, code="CB", events=[("ticket_work", 60, 200)])
        await InvoiceService(s).create_from_cycle(cyc.id)
        with pytest.raises(InvoiceAlreadyExists):
            await InvoiceService(s).create_from_cycle(cyc.id)


@pytest.mark.asyncio
async def test_transitions_paid_void_terminal(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_cycle_with_events(s, code="CB", events=[("ticket_work", 60, 200)])
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        paid = await InvoiceService(s).mark_paid(inv.id)
        assert paid.status == InvoiceStatus.paid
        # paid é terminal → não pode void
        with pytest.raises(InvoiceError):
            await InvoiceService(s).mark_void(inv.id)

        # nova fatura → void é terminal, não volta a open via mark_paid
        _c2, cyc2 = await _seed_cycle_with_events(s, code="CB2", events=[("ticket_work", 60, 200)])
        inv2 = await InvoiceService(s).create_from_cycle(cyc2.id)
        voided = await InvoiceService(s).mark_void(inv2.id)
        assert voided.status == InvoiceStatus.void
        with pytest.raises(InvoiceError):
            await InvoiceService(s).mark_paid(inv2.id)


@pytest.mark.asyncio
async def test_mark_overdue_due(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_cycle_with_events(s, code="CB", events=[("ticket_work", 60, 200)])
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        # força due_at no passado
        inv.due_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        await s.flush()
        n = await InvoiceService(s).mark_overdue_due(today=dt.date(2026, 6, 9))
        assert n == 1
        refreshed = await s.get(Invoice, inv.id)
        assert refreshed.status == InvoiceStatus.overdue

        # paid não vira overdue
        _c2, cyc2 = await _seed_cycle_with_events(s, code="CB2", events=[("ticket_work", 60, 200)])
        inv2 = await InvoiceService(s).create_from_cycle(cyc2.id)
        inv2.due_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        await InvoiceService(s).mark_paid(inv2.id)
        n2 = await InvoiceService(s).mark_overdue_due(today=dt.date(2026, 6, 9))
        assert n2 == 0
