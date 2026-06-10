"""Worker marca faturas vencidas como overdue (1x/dia, cross-tenant).

Dois níveis:
1. unit puro do tick (monkeypatch) — garante que mark_overdue_due é chamado 1x/dia;
2. integração real via InvoiceOverdueMarker — fatura open vencida → overdue; paid não muda.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.invoice_overdue import InvoiceOverdueMarker
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.jobs import worker
from gerti_sidecar.models import ContractCycle, Invoice
from gerti_sidecar.models.enums import ContractType, CycleKind, InvoiceStatus


@pytest.mark.asyncio
async def test_tick_calls_overdue_marker_daily(monkeypatch):
    calls = {"reconcile": 0, "close": 0, "overdue": 0}

    class FakeRecon:
        def __init__(self, gi):
            pass

        async def reconcile(self):
            calls["reconcile"] += 1
            return 0

    class FakeCloser:
        async def close_due_cycles(self):
            calls["close"] += 1
            return 0

    class FakeOverdue:
        async def mark_overdue_due(self):
            calls["overdue"] += 1
            return 0

    monkeypatch.setattr(worker, "ReconciliationService", FakeRecon)
    monkeypatch.setattr(worker, "CycleCloser", FakeCloser)
    monkeypatch.setattr(worker, "InvoiceOverdueMarker", FakeOverdue)

    state = worker.WorkerState(last_close_date=None)
    await worker.tick(state, today=dt.date(2026, 6, 9))
    assert calls == {"reconcile": 1, "close": 1, "overdue": 1}
    # mesmo dia: só reconcilia
    await worker.tick(state, today=dt.date(2026, 6, 9))
    assert calls == {"reconcile": 2, "close": 1, "overdue": 1}


async def _seed_invoice_due_past(s, code, *, due_at):
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
    await CycleService(s).close(cyc.id)
    inv = await InvoiceService(s).create_from_cycle(cyc.id)
    inv.due_at = due_at
    await s.flush()
    return inv


@pytest.mark.asyncio
async def test_overdue_marker_cross_tenant(
    engine, session, app_session_factory, seed_two_tenants, monkeypatch
):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        inv_a = await _seed_invoice_due_past(s, "A", due_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
        a_inv_id = inv_a.id
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        inv_b = await _seed_invoice_due_past(s, "B", due_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
        # paga a de B → não deve virar overdue
        await InvoiceService(s).mark_paid(inv_b.id)
        b_inv_id = inv_b.id

    # AdminSessionLocal = engine admin (BYPASSRLS-equiv); SessionLocal = app (RLS).
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    n = await InvoiceOverdueMarker().mark_overdue_due(today=dt.date(2026, 6, 9))
    assert n == 1

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        assert (await s.get(Invoice, a_inv_id)).status == InvoiceStatus.overdue
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        assert (await s.get(Invoice, b_inv_id)).status == InvoiceStatus.paid
