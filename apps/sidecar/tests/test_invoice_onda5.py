"""Onda 5 — as três dívidas financeiras da Onda 0, e a decisão D-Q.

Cada teste aqui corresponde a uma linha da tabela de dívida registrada:

1. **Glosa aprovada não abatia a fatura** (grave, pré-existente). O fechamento
   do ciclo já excluía o glosado; a fatura agregava por janela de data e
   cobrava assim mesmo. O cliente contestava 2 h, o gestor aprovava, e a
   cobrança saía com as 2 h dentro.
2. **Mensalidade não olhava o tamanho do ciclo** — um contrato trimestral
   cobrava um mês. É a decisão **D-Q**, que ficou aberta porque não havia
   gerador de ciclos para tornar o erro observável.
3. **Contrato suspenso cobrava mês cheio.**
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.invoice_service import (
    _KIND_LABELS,
    KIND_MONTHLY_FEE,
    InvoiceService,
    cycle_months,
)
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractCycle,
    Glosa,
    Invoice,
    InvoiceLine,
    Tenant,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import (
    ContractStatus,
    ContractType,
    CycleKind,
    CycleStatus,
    GlosaStatus,
)

D = dt.date


def test_cycle_months_counts_calendar_months():
    """Trimestral é 3 — contado por meses tocados, não por dias/30."""

    def c(a, b):
        return ContractCycle(contract_id=None, kind=CycleKind.closing, period_start=a, period_end=b)

    assert cycle_months(c(D(2026, 1, 1), D(2026, 1, 31))) == 1
    assert cycle_months(c(D(2026, 1, 1), D(2026, 3, 31))) == 3
    # 89 dias, mas três meses-calendário. Dividir por 30 daria 2.
    assert cycle_months(c(D(2026, 2, 1), D(2026, 4, 30))) == 3
    assert cycle_months(c(D(2026, 11, 1), D(2027, 1, 31))) == 3


async def _seed(session, *, ctype, status=ContractStatus.active, **contract_kw):
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
        code="C-1",
        type=ctype,
        status=status,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        created_by="seed",
        **contract_kw,
    )
    session.add(c)
    await session.flush()
    return t, c


async def _cycle(session, contract, start, end):
    cyc = ContractCycle(
        contract_id=contract.id,
        kind=CycleKind.closing,
        period_start=start,
        period_end=end,
        status=CycleStatus.closed,
        totals={},
    )
    session.add(cyc)
    await session.flush()
    return cyc


# ── 1. glosa aprovada ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approved_glosa_is_not_invoiced(engine, app_session_factory, session):
    """A dívida mais cara: cliente contesta, gestor aprova, e cobrava assim mesmo."""
    t, c = await _seed(
        session, ctype=ContractType.credit_brl, initial_amount_brl=10000, unit_price_brl=200
    )
    cyc = await _cycle(session, c, D(2026, 5, 1), D(2026, 5, 31))

    # Dois lançamentos: um limpo (R$ 600) e um contestado (R$ 400). A glosa
    # aponta PARA o evento — é assim que o modelo liga os dois.
    events = []
    for amount in (600.0, 400.0):
        ev = ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"znuny:ticket:{amount}",
            billable_minutes=180.0,
            billable_amount_brl=amount,
            recorded_by="seed",
        )
        session.add(ev)
        events.append(ev)
    await session.flush()

    glosa = Glosa(
        consumption_event_id=events[1].id,
        status=GlosaStatus.approved,
        reason="cliente contestou",
        requested_by="ana",
    )
    session.add(glosa)
    await session.flush()
    events[1].glosa_id = glosa.id
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        lines = (
            (await s.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)))
            .scalars()
            .all()
        )

    total = sum(line.amount_cents for line in lines)
    # Só os R$ 600 não-glosados. Com o defeito, sairiam R$ 1.000.
    assert total == 60000, f"a fatura cobrou glosa aprovada: {total} centavos"


# ── 2. D-Q: o tamanho do ciclo ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quarterly_cycle_bills_three_months(engine, app_session_factory, session):
    """D-Q assumido: o valor contratado é MENSAL, então trimestre cobra 3x."""
    t, c = await _seed(session, ctype=ContractType.closed_value, initial_amount_brl=1500)
    cyc = await _cycle(session, c, D(2026, 1, 1), D(2026, 3, 31))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        line = (
            (
                await s.execute(
                    select(InvoiceLine).where(
                        InvoiceLine.invoice_id == inv.id,
                        InvoiceLine.description == _KIND_LABELS[KIND_MONTHLY_FEE],
                    )
                )
            )
            .scalars()
            .one()
        )
    assert float(line.quantity) == 3.0
    assert line.amount_cents == 450000  # 3 x R$ 1.500


@pytest.mark.asyncio
async def test_contract_priced_per_cycle_bills_once(engine, app_session_factory, session):
    """O outro estado de D-Q: quem cotou por fechamento cobra 1x."""
    t, c = await _seed(
        session,
        ctype=ContractType.closed_value,
        initial_amount_brl=4500,
        billing_amount_period="cycle",
    )
    cyc = await _cycle(session, c, D(2026, 1, 1), D(2026, 3, 31))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        line = (
            (
                await s.execute(
                    select(InvoiceLine).where(
                        InvoiceLine.invoice_id == inv.id,
                        InvoiceLine.description == _KIND_LABELS[KIND_MONTHLY_FEE],
                    )
                )
            )
            .scalars()
            .one()
        )
    assert float(line.quantity) == 1.0
    assert line.amount_cents == 450000


@pytest.mark.asyncio
async def test_monthly_cycle_is_unchanged(engine, app_session_factory, session):
    """Regressão: o caso comum (ciclo mensal) continua cobrando 1x."""
    t, c = await _seed(session, ctype=ContractType.closed_value, initial_amount_brl=1500)
    cyc = await _cycle(session, c, D(2026, 5, 1), D(2026, 5, 31))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        line = (
            (
                await s.execute(
                    select(InvoiceLine).where(
                        InvoiceLine.invoice_id == inv.id,
                        InvoiceLine.description == _KIND_LABELS[KIND_MONTHLY_FEE],
                    )
                )
            )
            .scalars()
            .one()
        )
    assert float(line.quantity) == 1.0
    assert line.amount_cents == 150000


# ── 3. contrato suspenso ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suspended_contract_does_not_bill_the_monthly_fee(
    engine, app_session_factory, session
):
    """Serviço suspenso não gera mensalidade — mas o trabalho já feito é cobrado."""
    t, c = await _seed(
        session,
        ctype=ContractType.closed_value,
        status=ContractStatus.suspended,
        initial_amount_brl=1500,
    )
    cyc = await _cycle(session, c, D(2026, 5, 1), D(2026, 5, 31))
    session.add(
        ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref="znuny:ticket:1",
            billable_minutes=60.0,
            billable_amount_brl=200.0,
            recorded_by="seed",
        )
    )
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        lines = (
            (await s.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)))
            .scalars()
            .all()
        )
    kinds = {line.description for line in lines}
    assert (
        _KIND_LABELS[KIND_MONTHLY_FEE] not in kinds
    ), "contrato suspenso não pode cobrar mensalidade"
    # ...mas o consumo registrado continua na fatura: o trabalho foi feito.
    assert lines, "o consumo do período sumiu junto com a mensalidade"


@pytest.mark.asyncio
async def test_invoice_still_created_for_a_suspended_contract(engine, app_session_factory, session):
    """Suspender não pode fazer a emissão explodir — só zera a mensalidade."""
    t, c = await _seed(
        session,
        ctype=ContractType.saas_product,
        status=ContractStatus.suspended,
        initial_amount_brl=900,
    )
    cyc = await _cycle(session, c, D(2026, 5, 1), D(2026, 5, 31))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        found = await s.get(Invoice, inv.id)
    assert found is not None
    assert found.total_cents == 0
