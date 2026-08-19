"""T-R3.2 — bolsa de crédito compartilhada entre contratos.

*"A matriz compra o crédito e as filiais consomem daquele bolo."*

O defeito que isto corrige é silencioso e caro: `credit_shared` existia como
tipo desde o #0 e se comportava **igual** a `credit_brl`. Cada filial via a
bolsa inteira como sua, e o cliente podia gastar o crédito tantas vezes
quantas fossem as filiais. `test_before_this_each_branch_saw_the_whole_pool` é
o teste que fixa a correção.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.shared_pool_service import (
    NewSharedPool,
    SharedPoolError,
    SharedPoolService,
)
from gerti_sidecar.models import ConsumptionEvent, Contract, Glosa, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, GlosaStatus

D = dt.date


async def _seed(session):
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
        legal_name="Rede Sul",
        trade_name="Rede Sul",
        document="1",
        znuny_customer_id="SUL",
        znuny_instance_id=inst.id,
        subdomain="sul",
    )
    session.add(t)
    await session.flush()
    await session.commit()
    return t


async def _contract(s, code, *, ctype=ContractType.credit_shared, amount=10000):
    c = Contract(
        tenant_id=(await s.execute(select(Tenant.id))).scalar_one(),
        code=code,
        type=ctype,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        initial_amount_brl=amount,
        unit_price_brl=200,
        created_by="seed",
    )
    s.add(c)
    await s.flush()
    return c


async def _spend(s, contract_id, amount, ref):
    await ConsumptionService(s).record(
        RecordConsumption(
            contract_id=contract_id,
            occurred_at=dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=ref,
            billable_minutes=60.0,
            billable_amount_brl=amount,
            recorded_by="worker",
        )
    )


# ── o defeito corrigido ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_before_this_each_branch_saw_the_whole_pool(engine, app_session_factory, session):
    """Duas filiais na mesma bolsa veem UM saldo, e ele desce com o gasto de ambas."""
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa matriz", total_amount_brl=10000))
        filial_a = await _contract(s, "SUL-A")
        filial_b = await _contract(s, "SUL-B")
        await svc.link(pool.id, filial_a.id)
        await svc.link(pool.id, filial_b.id)

        await _spend(s, filial_a.id, 3000.0, "znuny:ticket:1")
        await _spend(s, filial_b.id, 2000.0, "znuny:ticket:2")

        bal_a = await ConsumptionService(s).balance(filial_a.id)
        bal_b = await ConsumptionService(s).balance(filial_b.id)

    # 10.000 - 3.000 - 2.000. Antes, cada uma veria a SUA conta:
    # A = 10.000 - 3.000 = 7.000 e B = 10.000 - 2.000 = 8.000.
    assert bal_a.remaining == 5000.0
    assert bal_b.remaining == 5000.0, "cada filial ainda tem a sua própria bolsa"


@pytest.mark.asyncio
async def test_an_unlinked_credit_contract_keeps_its_own_balance(
    engine, app_session_factory, session
):
    """Regressão: contrato de crédito sem bolsa continua como sempre."""
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        c = await _contract(s, "SUL-C", ctype=ContractType.credit_brl, amount=5000)
        await _spend(s, c.id, 1200.0, "znuny:ticket:9")
        bal = await ConsumptionService(s).balance(c.id)
    assert bal.remaining == 3800.0


@pytest.mark.asyncio
async def test_unlinking_gives_the_contract_its_own_balance_back(
    engine, app_session_factory, session
):
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa", total_amount_brl=10000))
        c = await _contract(s, "SUL-D", amount=4000)
        await svc.link(pool.id, c.id)
        await _spend(s, c.id, 1000.0, "znuny:ticket:5")
        assert (await ConsumptionService(s).balance(c.id)).remaining == 9000.0

        await svc.unlink(c.id)
        assert (await ConsumptionService(s).balance(c.id)).remaining == 3000.0


# ── regras de vínculo ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_only_shared_credit_contracts_can_join(engine, app_session_factory, session):
    """Banco de horas numa bolsa em reais deixaria 'quanto sobra?' sem resposta."""
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa", total_amount_brl=10000))
        horas = await _contract(s, "SUL-H", ctype=ContractType.hour_bank)
        with pytest.raises(SharedPoolError, match="crédito compartilhado"):
            await svc.link(pool.id, horas.id)


@pytest.mark.asyncio
async def test_a_pool_needs_a_positive_amount(engine, app_session_factory, session):
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(SharedPoolError, match="maior que zero"):
            await SharedPoolService(s).create(NewSharedPool(name="X", total_amount_brl=0))


# ── glosa ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_approved_glosa_returns_credit_to_the_pool(engine, app_session_factory, session):
    """A regra de glosa do financeiro vale igual dentro da bolsa."""
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa", total_amount_brl=10000))
        c = await _contract(s, "SUL-E")
        await svc.link(pool.id, c.id)
        await _spend(s, c.id, 2500.0, "znuny:ticket:7")
        ev = (await s.execute(select(ConsumptionEvent))).scalars().one()
        glosa = Glosa(
            consumption_event_id=ev.id,
            status=GlosaStatus.approved,
            reason="cobrado por engano",
            requested_by="cliente",
        )
        s.add(glosa)
        await s.flush()
        ev.glosa_id = glosa.id
        await s.flush()

        balance = await svc.balance(pool.id)
    assert balance.remaining_brl == 10000.0
    assert balance.consumed_brl == 0.0


# ── leitura da bolsa ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_pool_lists_its_contracts(engine, app_session_factory, session):
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa", total_amount_brl=1000))
        a = await _contract(s, "SUL-X")
        b = await _contract(s, "SUL-Y")
        await svc.link(pool.id, a.id)
        await svc.link(pool.id, b.id)
        codes = [c.code for c in await svc.contracts_in(pool.id)]
        pools = await svc.all_pools()
    assert codes == ["SUL-X", "SUL-Y"]
    assert [p.name for p in pools] == ["Bolsa"]


@pytest.mark.asyncio
async def test_an_empty_pool_is_fully_available(engine, app_session_factory, session):
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = SharedPoolService(s)
        pool = await svc.create(NewSharedPool(name="Bolsa", total_amount_brl=7500))
        bal = await svc.balance(pool.id)
    assert bal.remaining_brl == 7500.0
    assert bal.contract_ids == []
