"""T-R3.3 — contrato por pacote de atendimentos consome e cobra.

A dívida: `AUR-PACOTE-2026` existia, recebia chamados, e fechar o ciclo dele
gerava fatura de R$ 0,00. Três defeitos empilhados:

1. o saldo contava eventos de `source_kind='service_item'`, um kind que **nada
   no sistema jamais gravou** — o pacote nunca baixava;
2. o fechamento não calculava franquia nem excedente para o tipo;
3. a fatura não tinha linha nenhuma para ele.

A unidade é o **chamado**. Um chamado com três apontamentos de hora é um
atendimento, não três — é o teste que mais importa aqui.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.invoice_service import (
    _KIND_LABELS,
    KIND_SERVICE_INCLUDED,
    KIND_SERVICE_OVERAGE,
    InvoiceService,
)
from gerti_sidecar.models import Contract, ContractCycle, InvoiceLine, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus

D = dt.date


async def _seed(session, *, initial_service_count=10, unit_price_brl=150, accumulate=False):
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
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(t)
    await session.flush()
    c = Contract(
        tenant_id=t.id,
        code="AUR-PACOTE-2026",
        type=ContractType.service_count,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        initial_service_count=initial_service_count,
        unit_price_brl=unit_price_brl,
        accumulate_balance_between_cycles=accumulate,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    await session.commit()
    return t, c


async def _work(s, contract_id, *, ticket, minutes=60.0, day=10):
    await ConsumptionService(s).record(
        RecordConsumption(
            contract_id=contract_id,
            occurred_at=dt.datetime(2026, 5, day, 9, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"znuny:ticket:{ticket}",
            billable_minutes=minutes,
            recorded_by="worker:reconcile",
            znuny_ticket_id=ticket,
        )
    )


# Datas como constantes de módulo: `D(...)` em default de argumento é B008
# (o valor seria construído uma vez, na importação).
_MAY_START = D(2026, 5, 1)
_MAY_END = D(2026, 5, 31)


async def _cycle(s, contract_id, start=_MAY_START, end=_MAY_END):
    cyc = ContractCycle(
        contract_id=contract_id,
        kind=CycleKind.closing,
        period_start=start,
        period_end=end,
        status=CycleStatus.open,
    )
    s.add(cyc)
    await s.flush()
    return cyc


# ── o saldo baixa ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_package_actually_decreases(engine, app_session_factory, session):
    t, c = await _seed(session, initial_service_count=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for ticket in (101, 102, 103):
            await _work(s, c.id, ticket=ticket)
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.kind == "services"
    assert bal.remaining == 7, "o pacote não baixou — era a dívida T-R3.3"


@pytest.mark.asyncio
async def test_one_ticket_with_many_work_entries_is_one_service(
    engine, app_session_factory, session
):
    """O teste que define a unidade: atendimento é o CHAMADO."""
    t, c = await _seed(session, initial_service_count=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for day in (10, 11, 12):
            await _work(s, c.id, ticket=200, day=day)
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.remaining == 9, "três apontamentos no mesmo chamado viraram três atendimentos"


@pytest.mark.asyncio
async def test_consumption_without_a_ticket_counts_as_one_each(
    engine, app_session_factory, session
):
    """Item avulso (deslocamento, item de catálogo) não tem chamado e conta um."""
    t, c = await _seed(session, initial_service_count=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for i in range(2):
            await ConsumptionService(s).record(
                RecordConsumption(
                    contract_id=c.id,
                    occurred_at=dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC),
                    source_kind="travel",
                    source_ref=f"manual:{i}",
                    billable_minutes=0.0,
                    recorded_by="ana",
                )
            )
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.remaining == 8


# ── o fechamento calcula ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_closing_computes_franchise_and_overage(engine, app_session_factory, session):
    t, c = await _seed(session, initial_service_count=3, unit_price_brl=150)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for ticket in (301, 302, 303, 304, 305):
            await _work(s, c.id, ticket=ticket)
        cyc = await _cycle(s, c.id)
        totals = await CycleService(s).close(cyc.id)
    assert totals["consumed_services"] == 5
    assert totals["franchise_services"] == 3
    assert totals["overage_services"] == 2
    assert totals["overage_amount_brl"] == 300.0  # 2 x R$ 150


@pytest.mark.asyncio
async def test_within_the_package_there_is_no_overage(engine, app_session_factory, session):
    t, c = await _seed(session, initial_service_count=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for ticket in (401, 402):
            await _work(s, c.id, ticket=ticket)
        cyc = await _cycle(s, c.id)
        totals = await CycleService(s).close(cyc.id)
    assert totals["overage_services"] == 0
    assert totals["overage_amount_brl"] == 0.0


# ── a fatura cobra ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_invoice_is_no_longer_zero(engine, app_session_factory, session):
    """O sintoma original: fechar o ciclo do pacote gerava fatura R$ 0,00."""
    t, c = await _seed(session, initial_service_count=3, unit_price_brl=150)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        for ticket in (501, 502, 503, 504, 505):
            await _work(s, c.id, ticket=ticket)
        cyc = await _cycle(s, c.id)
        await CycleService(s).close(cyc.id)
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        lines = (
            (
                await s.execute(
                    select(InvoiceLine)
                    .where(InvoiceLine.invoice_id == inv.id)
                    .order_by(InvoiceLine.position)
                )
            )
            .scalars()
            .all()
        )
    by_desc = {line.description: line for line in lines}
    incluidos = by_desc[_KIND_LABELS[KIND_SERVICE_INCLUDED]]
    excedentes = by_desc[_KIND_LABELS[KIND_SERVICE_OVERAGE]]
    assert float(incluidos.quantity) == 3.0
    assert incluidos.amount_cents == 0
    assert incluidos.unit == "atendimento"
    assert float(excedentes.quantity) == 2.0
    assert excedentes.amount_cents == 30000
    assert inv.total_cents == 30000, "a fatura do pacote continuou zerada"


@pytest.mark.asyncio
async def test_the_invoice_does_not_mix_hours_into_the_package(
    engine, app_session_factory, session
):
    """Pacote é contado em atendimento; hora na mesma fatura confundiria a conta."""
    t, c = await _seed(session, initial_service_count=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _work(s, c.id, ticket=601, minutes=180.0)
        cyc = await _cycle(s, c.id)
        await CycleService(s).close(cyc.id)
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        units = {
            line.unit
            for line in (
                await s.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
            )
            .scalars()
            .all()
        }
    assert units == {"atendimento"}


@pytest.mark.asyncio
async def test_a_cycle_closed_before_onda5_bills_nothing_instead_of_guessing(
    engine, app_session_factory, session
):
    """Snapshot antigo não contou atendimento; inventar número agora seria pior."""
    t, c = await _seed(session, initial_service_count=3)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=D(2026, 5, 1),
            period_end=D(2026, 5, 31),
            status=CycleStatus.closed,
            totals={"consumed_minutes": 300.0},  # sem *_services
        )
        s.add(cyc)
        await s.flush()
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
    assert inv.total_cents == 0


# ── acúmulo de atendimentos entre ciclos (D-R) ──────────────────────────────


@pytest.mark.asyncio
async def test_unused_services_carry_over_when_the_contract_says_so(
    engine, app_session_factory, session
):
    t, c = await _seed(session, initial_service_count=10, accumulate=True)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _work(s, c.id, ticket=701)
        first = await _cycle(s, c.id, D(2026, 5, 1), D(2026, 5, 31))
        totals = await CycleService(s).close(first.id)
        assert totals["carry_over"] == 9.0

        # Junho: franquia efetiva = 10 do mês + 9 acumulados = 19.
        for ticket in range(800, 812):  # 12 atendimentos
            await ConsumptionService(s).record(
                RecordConsumption(
                    contract_id=c.id,
                    occurred_at=dt.datetime(2026, 6, 5, 9, tzinfo=dt.UTC),
                    source_kind="ticket_work",
                    source_ref=f"znuny:ticket:{ticket}",
                    billable_minutes=60.0,
                    recorded_by="worker:reconcile",
                    znuny_ticket_id=ticket,
                )
            )
        second = await _cycle(s, c.id, D(2026, 6, 1), D(2026, 6, 30))
        totals2 = await CycleService(s).close(second.id)
    assert totals2["franchise_services"] == 19.0
    assert totals2["overage_services"] == 0.0
    assert totals2["carry_over"] == 7.0
