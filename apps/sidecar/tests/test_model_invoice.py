"""Invoice + InvoiceLine: model, UNIQUE (tenant_id, number), CHECK, FK, RLS.

Espelha o padrão de test_model_cycle_consumption.py. invoice/invoice_line são
tenant-scoped (FORCE RLS + policy direta por tenant_id denormalizado).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gerti_sidecar import db
from gerti_sidecar.models import Contract, Invoice, InvoiceLine
from gerti_sidecar.models.enums import ContractType, InvoiceStatus


async def _seed_contract(session, tenant_id, code):
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
    return c


@pytest.mark.asyncio
async def test_invoice_unique_number_and_lines(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = await _seed_contract(session, a_id, "C1")
    inv = Invoice(
        tenant_id=a_id,
        contract_id=c.id,
        number=1,
        status=InvoiceStatus.open,
        issued_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
        due_at=dt.datetime(2026, 2, 16, tzinfo=dt.UTC),
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
        subtotal_cents=10000,
        total_cents=10000,
    )
    session.add(inv)
    await session.flush()
    assert inv.currency == "BRL"

    line = InvoiceLine(
        invoice_id=inv.id,
        tenant_id=a_id,
        description="Banco de horas",
        quantity=2,
        unit="h",
        unit_price_cents=5000,
        amount_cents=10000,
        position=0,
    )
    session.add(line)
    await session.flush()

    # UNIQUE (tenant_id, number): segundo invoice com number=1 no mesmo tenant falha
    dup = Invoice(
        tenant_id=a_id,
        contract_id=c.id,
        number=1,
        status=InvoiceStatus.open,
        issued_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
        due_at=dt.datetime(2026, 2, 16, tzinfo=dt.UTC),
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
        subtotal_cents=0,
        total_cents=0,
    )
    sp = await session.begin_nested()
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()


@pytest.mark.asyncio
async def test_invoice_total_cents_non_negative(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    c = await _seed_contract(session, a_id, "C2")
    bad = Invoice(
        tenant_id=a_id,
        contract_id=c.id,
        number=5,
        status=InvoiceStatus.open,
        issued_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
        due_at=dt.datetime(2026, 2, 16, tzinfo=dt.UTC),
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
        subtotal_cents=0,
        total_cents=-1,
    )
    sp = await session.begin_nested()
    session.add(bad)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()


@pytest.mark.asyncio
async def test_invoice_rls_isolation(session, app_session_factory, seed_two_tenants):
    """Tenant A só vê suas faturas/linhas; B vê só as dele; GUC ausente → 0 linhas."""
    a_id, b_id = seed_two_tenants

    async def _seed(tenant_id, code, number):
        c = await _seed_contract(session, tenant_id, code)
        inv = Invoice(
            tenant_id=tenant_id,
            contract_id=c.id,
            number=number,
            status=InvoiceStatus.open,
            issued_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
            due_at=dt.datetime(2026, 2, 16, tzinfo=dt.UTC),
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
            subtotal_cents=100,
            total_cents=100,
        )
        session.add(inv)
        await session.flush()
        session.add(
            InvoiceLine(
                invoice_id=inv.id,
                tenant_id=tenant_id,
                description=code,
                quantity=1,
                unit="h",
                unit_price_cents=100,
                amount_cents=100,
                position=0,
            )
        )
        await session.flush()

    await _seed(a_id, "A", 1)
    await _seed(b_id, "B", 1)
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        invs = (await s.execute(text("SELECT number FROM gerti.invoice"))).scalars().all()
        lines = (
            (await s.execute(text("SELECT description FROM gerti.invoice_line"))).scalars().all()
        )
    assert invs == [1]
    assert lines == ["A"]

    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        lines = (
            (await s.execute(text("SELECT description FROM gerti.invoice_line"))).scalars().all()
        )
    assert lines == ["B"]

    # GUC ausente → fail-closed
    async with app_session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM gerti.invoice"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM gerti.invoice_line"))).scalar_one() == 0
