"""InvoiceService: create_from_cycle idempotente, numeração sequencial, transições.

Seed de contrato + ciclo de fechamento + consumption_events; a fatura agrega as
linhas por source_kind, numera sequencialmente por tenant, e é idempotente por
ciclo (InvoiceAlreadyExists). mark_paid/mark_void aplicam transições; paid/void
são terminais.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.errors import InvoiceAlreadyExists, InvoiceError
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import ContractCycle, Invoice
from gerti_sidecar.models.enums import ContractType, CycleKind, InvoiceStatus


async def _seed_typed_cycle(s, *, code, ctype, events, **contract_fields):
    """Contrato de `ctype` + ciclo de fechamento fechado + eventos de consumo."""
    c = await ContractService(s).create(
        NewContract(
            code=code,
            type=ctype,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            created_by="w",
            **contract_fields,
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


async def _seed_cycle_with_events(s, *, code, events):
    return await _seed_typed_cycle(
        s,
        code=code,
        ctype=ContractType.credit_brl,
        events=events,
        initial_amount_brl=20000,
        unit_price_brl=200,
    )


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
async def test_hour_bank_overage_is_billed(session, app_session_factory, seed_two_tenants):
    """V-R15.4 — banco de horas: franquia 10h, 12h consumidas, R$ 200/h → R$ 400,00.

    Os eventos de `hour_bank` nascem com billable_amount_brl = 0 (o worker só
    precifica tipos de crédito — reconciliation_service). O valor da fatura vem
    do overage calculado no fechamento do ciclo.

    As linhas em horas precisam SOMAR 12 h — o consumido. Emitir "Atendimento
    (horas) 12 h" + "Horas excedentes 2 h" mostrava 14 h ao cliente, contando o
    excedente duas vezes (as 2 h estão DENTRO das 12 h).
    """
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_typed_cycle(
            s,
            code="HB1",
            ctype=ContractType.hour_bank,
            events=[("ticket_work", 12 * 60, 0)],
            initial_hours=10,
            unit_price_brl=200,
        )
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        assert inv.total_cents == 40000
        assert inv.subtotal_cents == 40000

        lines = await InvoiceService(s).lines_for(inv.id)
        # Rótulo, quantidade e valor de CADA linha — nada de dobra de horas.
        assert [
            (line.description, float(line.quantity), line.unit, line.amount_cents) for line in lines
        ] == [
            ("Horas dentro da franquia", 10.0, "h", 0),
            ("Horas excedentes", 2.0, "h", 40000),
        ]
        # A soma das quantidades em horas é o consumido (12 h), não 14 h.
        assert sum(float(line.quantity) for line in lines if line.unit == "h") == 12.0

        overage = [line for line in lines if line.description == "Horas excedentes"]
        assert overage[0].unit_price_cents == 20000


@pytest.mark.asyncio
async def test_hour_bank_within_franchise_has_no_overage_line(
    session, app_session_factory, seed_two_tenants
):
    """Dentro da franquia não há linha de excedente — fatura zerada é legítima."""
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_typed_cycle(
            s,
            code="HB2",
            ctype=ContractType.hour_bank,
            events=[("ticket_work", 6 * 60, 0)],
            initial_hours=10,
            unit_price_brl=200,
        )
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        lines = await InvoiceService(s).lines_for(inv.id)
        # 6 h de 10 h: uma linha só, com as horas de fato consumidas.
        assert [(line.description, float(line.quantity)) for line in lines] == [
            ("Horas dentro da franquia", 6.0)
        ]
        assert inv.total_cents == 0


@pytest.mark.asyncio
async def test_hour_bank_travel_line_survives_franchise_clamp(
    session, app_session_factory, seed_two_tenants
):
    """O recorte da franquia só toca linhas em horas; deslocamento continua intacto."""
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_typed_cycle(
            s,
            code="HB3",
            ctype=ContractType.hour_bank,
            events=[("ticket_work", 12 * 60, 0), ("travel", 0, 50)],
            initial_hours=10,
            unit_price_brl=200,
        )
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        lines = await InvoiceService(s).lines_for(inv.id)
        assert [(line.description, float(line.quantity), line.amount_cents) for line in lines] == [
            ("Horas dentro da franquia", 10.0, 0),
            ("Deslocamento", 1.0, 5000),
            ("Horas excedentes", 2.0, 40000),
        ]
        assert inv.total_cents == 45000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ctype", [ContractType.closed_value, ContractType.saas_product], ids=lambda t: t.value
)
async def test_fixed_value_contract_bills_monthly_fee(
    session, app_session_factory, seed_two_tenants, ctype
):
    """closed_value/saas_product: linha de mensalidade com o valor contratado."""
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_typed_cycle(
            s,
            code=f"FX-{ctype.value}",
            ctype=ctype,
            events=[("ticket_work", 90, 0)],
            initial_amount_brl=5000,
        )
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        assert inv.total_cents == 500000
        assert inv.subtotal_cents == 500000

        lines = await InvoiceService(s).lines_for(inv.id)
        fee = [line for line in lines if line.description == "Mensalidade"]
        assert len(fee) == 1
        assert fee[0].amount_cents == 500000
        assert fee[0].unit == "mês"
        assert float(fee[0].quantity) == 1.0
        assert fee[0].unit_price_cents == 500000
        # a mensalidade abre a fatura; o consumo vem depois
        assert fee[0].position == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ctype", [ContractType.credit_brl, ContractType.credit_shared], ids=lambda t: t.value
)
async def test_credit_contracts_unchanged(session, app_session_factory, seed_two_tenants, ctype):
    """Regressão: contratos de crédito continuam faturando só o consumo, sem linha nova."""
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_typed_cycle(
            s,
            code=f"CR-{ctype.value}",
            ctype=ctype,
            events=[("ticket_work", 60, 200), ("travel", 0, 50)],
            initial_amount_brl=20000,
            unit_price_brl=200,
        )
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        assert inv.total_cents == 25000
        lines = await InvoiceService(s).lines_for(inv.id)
        assert [line.description for line in lines] == ["Atendimento (horas)", "Deslocamento"]


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
