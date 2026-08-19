"""V-R11.3 — a agenda vira chamado, e **não duplica** (T-R11.3, R11).

O aceite é literal: *"rodar duas vezes no mesmo dia gera um chamado, não
dois"*. É o tipo de garantia que costuma ser escrita como um `if` e quebrar na
primeira concorrência — aqui ela é do banco (`UNIQUE(task_id,
occurrence_date)`), e estes testes existem para provar isso, inclusive no
caminho em que o worker reinicia.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.recurring_task_service import RecurringTaskService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import (
    Contract,
    RecurringTask,
    RecurringTaskRun,
    Tenant,
    TicketContractLink,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType

D = dt.date


class _GI:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self._fail = fail
        self._next = 900

    async def create_ticket(self, **kw):
        self.calls.append(kw)
        if self._fail:
            raise RuntimeError("znuny fora do ar")
        self._next += 1
        return znuny_ticket.TicketCreated(self._next, f"NUM{self._next}")


async def _seed(session: AsyncSession, **over) -> tuple[Tenant, RecurringTask, Contract]:
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
        code="AUR-HORAS",
        type=ContractType.hour_bank,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    fields = {
        "tenant_id": t.id,
        "title": "Verificação de backup",
        "body": "Conferir o backup noturno dos servidores.",
        "frequency": "weekly",
        "weekday": 0,  # segunda
        "at_time": dt.time(8, 0),
        "starts_on": D(2026, 8, 1),
        "znuny_queue_name": "Preventivos",
        "customer_user_login": "mariana.bianchi",
        "created_by": "william",
    }
    fields.update(over)
    task = RecurringTask(**fields)
    session.add(task)
    await session.commit()
    return t, task, c


@pytest.mark.asyncio
async def test_due_task_becomes_a_ticket(engine, app_session_factory, session):
    t, task, _c = await _seed(session)
    gi = _GI()
    # 2026-08-24 é uma segunda-feira.
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    assert r.created == 1
    call = gi.calls[0]
    assert call["title"] == "Verificação de backup"
    assert call["queue"] == "Preventivos"
    assert call["customer_user"] == "mariana.bianchi"


@pytest.mark.asyncio
async def test_running_twice_the_same_day_creates_one_ticket(engine, app_session_factory, session):
    """O aceite do T-R11.3, ao pé da letra."""
    t, _task, _c = await _seed(session)
    gi = _GI()
    for _ in range(2):
        async with tenant_session_scope(t.id, factory=app_session_factory) as s:
            await RecurringTaskService(s, gi).materialize(
                tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
            )
    assert len(gi.calls) == 1, "a agenda do técnico duplicou"

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        runs = (await s.execute(select(RecurringTaskRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].occurrence_date == D(2026, 8, 24)


@pytest.mark.asyncio
async def test_a_missed_day_is_still_materialized(engine, app_session_factory, session):
    """Worker fora do ar por dois dias não pode deixar buraco na agenda."""
    t, _task, _c = await _seed(session)
    gi = _GI()
    # Roda só na quarta (26/08): a ocorrência de segunda (24/08) ainda vale.
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 26)
        )
    assert r.created == 1
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        run = (await s.execute(select(RecurringTaskRun))).scalars().one()
    assert run.occurrence_date == D(2026, 8, 24)


@pytest.mark.asyncio
async def test_occurrences_older_than_the_window_are_not_backfilled(
    engine, app_session_factory, session
):
    """Tarefa antiga processada hoje NÃO abre os chamados retroativos.

    Erro de desenho que o teste pegou antes do deploy: a primeira versão
    caminhava desde `starts_on` e abriria, um por vez, todas as segundas-feiras
    desde o cadastro. Ninguém quer chegar na segunda com trinta "verificação de
    backup" de meses que já passaram.
    """
    t, _task, _c = await _seed(session, starts_on=D(2026, 1, 5))
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    # Só a ocorrência mais recente, nunca as de janeiro a agosto.
    assert r.created == 1
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        runs = (await s.execute(select(RecurringTaskRun))).scalars().all()
    assert [x.occurrence_date for x in runs] == [D(2026, 8, 24)]


@pytest.mark.asyncio
async def test_inactive_task_is_not_materialized(engine, app_session_factory, session):
    t, _task, _c = await _seed(session, active=False)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    assert r.created == 0
    assert gi.calls == []


@pytest.mark.asyncio
async def test_task_without_contract_does_not_link_one(engine, app_session_factory, session):
    """Suposição S4: preventiva NÃO consome contrato por padrão."""
    t, _task, _c = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
        links = (await s.execute(select(TicketContractLink))).scalars().all()
    assert links == [], "preventiva sem contrato não pode debitar saldo do cliente"


@pytest.mark.asyncio
async def test_task_with_contract_links_it(engine, app_session_factory, session):
    """...mas quem QUER faturar a preventiva, vincula — as duas leituras cabem."""
    t, task, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        obj = await s.get(RecurringTask, task.id)
        assert obj is not None
        obj.contract_id = c.id
        await s.flush()

    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        link = (await s.execute(select(TicketContractLink))).scalars().one()
    assert link.contract_id == c.id
    assert "recurring:" in link.linked_by_rule


@pytest.mark.asyncio
async def test_a_failure_is_recorded_and_not_retried_silently(engine, app_session_factory, session):
    """Falha vira linha com erro — visível —, não tentativa infinita.

    É a contrapartida honesta de gravar a marca antes do chamado: preferimos a
    falha visível ao risco de abrir o mesmo chamado duas vezes.
    """
    t, _task, _c = await _seed(session)
    gi = _GI(fail=True)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    assert r.failed == 1
    assert r.created == 0

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        run = (await s.execute(select(RecurringTaskRun))).scalars().one()
    assert run.znuny_ticket_id is None
    assert "znuny fora do ar" in (run.error or "")

    # E uma segunda passada NÃO tenta de novo — a ocorrência já está marcada.
    gi2 = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await RecurringTaskService(s, gi2).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24)
        )
    assert gi2.calls == []


@pytest.mark.asyncio
async def test_three_missed_occurrences_become_one_ticket(engine, app_session_factory, session):
    """Três backups atrasados não viram três chamados idênticos.

    O trabalho é o mesmo — "verifique o backup" —, e o técnico precisa de um
    chamado, não de uma pilha. Janela larga de propósito para forçar o caso.
    """
    t, _task, _c = await _seed(session, starts_on=D(2026, 8, 1))
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        r = await RecurringTaskService(s, gi).materialize(
            tenant_id=t.id, customer_id="AURORA", today=D(2026, 8, 24), catch_up_days=30
        )
    assert r.created == 1
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        runs = (await s.execute(select(RecurringTaskRun))).scalars().all()
    # A MAIS RECENTE, não a mais antiga: é a que ainda faz sentido atender.
    assert [x.occurrence_date for x in runs] == [D(2026, 8, 24)]
