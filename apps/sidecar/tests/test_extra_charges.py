"""T-R15.3 / T-R15.2 — lançamento avulso e cobrança do contrato livre.

*"Deslocamento, hora extra, aquele serviço que não estava no contrato."*

O que se prova aqui:

* o lançamento **chega na fatura** (senão a tela seria enfeite);
* ele **pode ser contestado** — um deslocamento indevido tem de poder virar
  glosa como qualquer consumo, e é a razão de o lançamento ser um
  `consumption_event` e não uma tabela paralela;
* deslocamento **não come franquia de hora**;
* o contrato **livre** existe e fatura só o que foi lançado (T-R15.2).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.extra_charge_service import (
    ExtraChargeError,
    ExtraChargeService,
    NewExtraCharge,
)
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import (
    Contract,
    ContractCycle,
    Glosa,
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


async def _seed(session, *, ctype=ContractType.hour_bank, status=ContractStatus.active, **kw):
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
    defaults = {"initial_hours": 10} if ctype == ContractType.hour_bank else {}
    defaults.update(kw)
    c = Contract(
        tenant_id=t.id,
        code="C-1",
        type=ctype,
        status=status,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        unit_price_brl=200,
        created_by="seed",
        **defaults,
    )
    session.add(c)
    await session.flush()
    await session.commit()
    return t, c


def _charge(contract_id, **kw):
    base = dict(
        contract_id=contract_id,
        kind="travel",
        description="Deslocamento até o cliente",
        amount_brl=80.0,
        recorded_by="ana",
        occurred_on=D(2026, 5, 10),
    )
    base.update(kw)
    return NewExtraCharge(**base)


# ── validação ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_kind_is_refused(engine, app_session_factory, session):
    """Kind livre viraria rótulo cru na fatura do cliente."""
    t, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ExtraChargeError, match="desconhecido"):
            await ExtraChargeService(s).add(_charge(c.id, kind="qualquer_coisa"))


@pytest.mark.asyncio
async def test_description_is_required(engine, app_session_factory, session):
    t, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ExtraChargeError, match="descreva"):
            await ExtraChargeService(s).add(_charge(c.id, description="   "))


@pytest.mark.asyncio
async def test_a_terminated_contract_refuses_new_charges(engine, app_session_factory, session):
    """Cobrança em contrato morto é a que ninguém consegue explicar depois."""
    t, c = await _seed(session, status=ContractStatus.terminated)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ExtraChargeError, match="terminated"):
            await ExtraChargeService(s).add(_charge(c.id))


@pytest.mark.asyncio
async def test_a_suspended_contract_still_accepts(engine, app_session_factory, session):
    """Serviço parado pode ter deslocamento pendente de lançar."""
    t, c = await _seed(session, status=ContractStatus.suspended)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        ev = await ExtraChargeService(s).add(_charge(c.id))
    assert float(ev.billable_amount_brl) == 80.0


@pytest.mark.asyncio
async def test_a_date_before_the_contract_is_refused(engine, app_session_factory, session):
    t, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ExtraChargeError, match="anterior ao início"):
            await ExtraChargeService(s).add(_charge(c.id, occurred_on=D(2025, 12, 31)))


@pytest.mark.asyncio
async def test_quantity_multiplies_the_amount(engine, app_session_factory, session):
    t, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        ev = await ExtraChargeService(s).add(_charge(c.id, amount_brl=80.0, quantity=3))
    assert float(ev.billable_amount_brl) == 240.0


# ── o que o lançamento NÃO faz ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_travel_does_not_eat_the_hour_franchise(engine, app_session_factory, session):
    """R$ 80 de deslocamento não podem consumir minuto nenhum do banco."""
    t, c = await _seed(session, initial_hours=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ExtraChargeService(s).add(_charge(c.id))
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.kind == "hours"
    assert bal.remaining == 10.0, "o deslocamento comeu franquia de hora"


@pytest.mark.asyncio
async def test_explicit_minutes_do_count(engine, app_session_factory, session):
    """Hora avulsa lançada de propósito conta — é o outro lado da regra."""
    t, c = await _seed(session, initial_hours=10)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ExtraChargeService(s).add(
            _charge(c.id, kind="ticket_work", description="Hora extra sábado", minutes=120)
        )
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.remaining == 8.0


# ── o lançamento chega na fatura, e pode ser contestado ─────────────────────


@pytest.mark.asyncio
async def test_the_charge_reaches_the_invoice(engine, app_session_factory, session):
    t, c = await _seed(session, ctype=ContractType.free)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ExtraChargeService(s).add(_charge(c.id, amount_brl=80.0, quantity=2))
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=D(2026, 5, 1),
            period_end=D(2026, 5, 31),
            status=CycleStatus.open,
        )
        s.add(cyc)
        await s.flush()
        await CycleService(s).close(cyc.id)
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
        lines = (
            (await s.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)))
            .scalars()
            .all()
        )
    assert [line.description for line in lines] == ["Deslocamento"]
    assert inv.total_cents == 16000


@pytest.mark.asyncio
async def test_a_charge_can_be_contested_like_any_consumption(engine, app_session_factory, session):
    """A razão de ser um consumption_event: glosa de graça, sem código novo."""
    t, c = await _seed(session, ctype=ContractType.free)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        ev = await ExtraChargeService(s).add(_charge(c.id))
        glosa = Glosa(
            consumption_event_id=ev.id,
            status=GlosaStatus.approved,
            reason="visita não aconteceu",
            requested_by="cliente",
        )
        s.add(glosa)
        await s.flush()
        ev.glosa_id = glosa.id
        await s.flush()

        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=D(2026, 5, 1),
            period_end=D(2026, 5, 31),
            status=CycleStatus.open,
        )
        s.add(cyc)
        await s.flush()
        await CycleService(s).close(cyc.id)
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        await s.flush()
    assert inv.total_cents == 0, "deslocamento glosado foi cobrado assim mesmo"


# ── T-R15.2: o contrato livre ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_free_contract_needs_no_initial_amount(engine, app_session_factory, session):
    """D-D: o cliente avulso ganha contrato livre em vez de consumo órfão.

    Todo outro tipo exige um campo inicial; o livre não exige nenhum. A
    indexação direta em `_REQUIRED` daria KeyError → 500 na criação.
    """
    from gerti_sidecar.domain.contract_service import ContractService, NewContract

    t, _ = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        created = await ContractService(s).create(
            NewContract(
                code="AVULSO-2026",
                type=ContractType.free,
                starts_on=D(2026, 1, 1),
                ends_on=D(2026, 12, 31),
                created_by="ana",
            )
        )
    assert created.type == ContractType.free
    assert created.initial_amount_brl is None
