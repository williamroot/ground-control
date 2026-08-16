"""ContractReadService: S3 glosa predicate + consumed_percent + series + low_balance.

Asserts the centralized rule matches ConsumptionService.balance() and that
pending/rejected/absent glosas COUNT while approved glosas do NOT. Uses the
admin session for setup (BYPASSRLS); the service is pure-read.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import ContractReadService
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractCycle,
    Glosa,
    Tenant,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, CycleKind, GlosaStatus


async def _tenant(session) -> Tenant:
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
        legal_name="A",
        trade_name="A",
        document="1",
        znuny_customer_id="A",
        znuny_instance_id=inst.id,
        subdomain="a",
    )
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_consumed_percent_and_glosa_rule_match_balance(session):
    t = await _tenant(session)
    c = Contract(
        tenant_id=t.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=10,
        unit_price_brl=100,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    # 60 + 120 + 60 min = 4h consumed if all count.
    evs = []
    for i, m in enumerate((60, 120, 60)):
        ev = ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"r{i}",
            billable_minutes=m,
            recorded_by="seed",
        )
        session.add(ev)
        await session.flush()
        evs.append(ev)
    # APPROVED glosa on the 120-min event -> it must NOT count.
    g_app = Glosa(
        consumption_event_id=evs[1].id, status=GlosaStatus.approved, reason="x", requested_by="seed"
    )
    session.add(g_app)
    await session.flush()
    # back-pointer: balance() keys on consumption_event.glosa_id (H8, app-layer, no FK)
    evs[1].glosa_id = g_app.id
    await session.flush()
    # PENDING glosa on the last 60-min event -> it STILL counts (no back-pointer on purpose).
    session.add(
        Glosa(
            consumption_event_id=evs[2].id,
            status=GlosaStatus.pending,
            reason="y",
            requested_by="seed",
        )
    )
    await session.flush()

    svc = ContractReadService(session)
    bal = await ConsumptionService(session).balance(c.id)
    # remaining = 10h - (60+60)/60 = 8.0  (120-min approved-glosa event excluded)
    assert bal.remaining == pytest.approx(8.0)
    pct = await svc.consumed_percent(c)
    # consumed 2h of 10h -> 20%
    assert pct == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_consumed_percent_none_for_closed_and_zero_initial(session):
    t = await _tenant(session)
    cv = Contract(
        tenant_id=t.id,
        code="CV",
        type=ContractType.closed_value,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=9000,
        unit_price_brl=9000,
        created_by="seed",
    )
    hb0 = Contract(
        tenant_id=t.id,
        code="HB0",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=0,
        unit_price_brl=100,
        created_by="seed",
    )
    session.add_all([cv, hb0])
    await session.flush()
    assert await ContractReadService(session).consumed_percent(cv) is None
    assert await ContractReadService(session).consumed_percent(hb0) is None


# ── R18a / S3 — a janela de "últimos três meses" ────────────────────────────
#
# *"vejo nos últimos três meses qual foi o ciclo de utilização dele"* (11:00).
#
# Não sabemos se ele quis mês-calendário ou ciclo de faturamento. Os dois modos
# coexistem e são testados nos dois estados; a chave `CONSUMPTION_WINDOW_MODE`
# só escolhe o padrão, e a rota aceita `?window=`.


async def _seed_windowed(session, *, contract_type=ContractType.hour_bank):
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
        subdomain="acme-win",
    )
    session.add(t)
    await session.flush()
    kwargs = {"initial_hours": 1000} if contract_type == ContractType.hour_bank else {}
    if contract_type == ContractType.credit_brl:
        kwargs = {"initial_amount_brl": 100000, "unit_price_brl": 200}
    c = Contract(
        tenant_id=t.id,
        code="C-WIN",
        type=contract_type,
        starts_on=dt.date(2025, 9, 1),
        ends_on=dt.date(2026, 12, 31),
        created_by="seed",
        **kwargs,
    )
    session.add(c)
    await session.commit()
    return t, c


def _event(contract_id, when: dt.datetime, minutes: float, amount: float = 0.0):
    return ConsumptionEvent(
        contract_id=contract_id,
        occurred_at=when,
        source_kind="ticket_work",
        source_ref=f"znuny:ticket:{when.isoformat()}",
        billable_minutes=minutes,
        billable_amount_brl=amount,
        recorded_by="seed",
    )


@pytest.mark.asyncio
async def test_series_months_window_has_exactly_three_points(engine, app_session_factory, session):
    """V-R18a.3 / aceite A18a.3 — 3 pontos, e o consumo velho NÃO aparece."""
    t, c = await _seed_windowed(session)
    # M-1 (julho) e M-5 (março). Só julho pode entrar numa janela de 3 meses
    # terminando em agosto.
    session.add(_event(c.id, dt.datetime(2026, 7, 10, 9, tzinfo=dt.UTC), 120.0))
    session.add(_event(c.id, dt.datetime(2026, 3, 10, 9, tzinfo=dt.UTC), 600.0))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(
            c, window="months", count=3, today=dt.date(2026, 8, 15)
        )

    assert series.kind == "hours"
    assert len(series.points) == 3
    assert [p.bucket for p in series.points] == [
        dt.date(2026, 6, 1),
        dt.date(2026, 7, 1),
        dt.date(2026, 8, 1),
    ]
    assert [p.value for p in series.points] == [0.0, 2.0, 0.0]
    # Assert de EXCLUSÃO, não só de tamanho: as 10 h de março sumiram mesmo.
    assert sum(p.value for p in series.points) == 2.0


@pytest.mark.asyncio
async def test_series_cycles_window_follows_the_billing_cycle(engine, app_session_factory, session):
    """S3 — no modo `cycles`, os pontos são CICLOS, que podem não ser mensais.

    Ciclos bimestrais: 3 pontos cobrem 6 meses. É a diferença que faz a
    suposição importar — e é por isso que os dois modos existem.
    """
    t, c = await _seed_windowed(session)
    for start, end in (
        (dt.date(2026, 3, 1), dt.date(2026, 4, 30)),
        (dt.date(2026, 5, 1), dt.date(2026, 6, 30)),
        (dt.date(2026, 7, 1), dt.date(2026, 8, 31)),
    ):
        session.add(
            ContractCycle(
                contract_id=c.id,
                kind=CycleKind.closing,
                period_start=start,
                period_end=end,
            )
        )
    # 3 h no 1º ciclo, 1 h no 3º.
    session.add(_event(c.id, dt.datetime(2026, 3, 15, 9, tzinfo=dt.UTC), 180.0))
    session.add(_event(c.id, dt.datetime(2026, 8, 2, 9, tzinfo=dt.UTC), 60.0))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(
            c, window="cycles", count=3, today=dt.date(2026, 8, 15)
        )

    assert series.granularity == "cycles"
    assert len(series.points) == 3
    assert [p.bucket for p in series.points] == [
        dt.date(2026, 3, 1),
        dt.date(2026, 5, 1),
        dt.date(2026, 7, 1),
    ]
    assert [p.value for p in series.points] == [3.0, 0.0, 1.0]


@pytest.mark.asyncio
async def test_cycles_without_any_cycle_falls_back_to_months(engine, app_session_factory, session):
    """Contrato sem ciclo nenhum não pode devolver gráfico vazio.

    Vazio se lê como "não consumiu nada", que é diferente de "ainda não
    fechamos ciclo". O fallback para meses diz a verdade.
    """
    t, c = await _seed_windowed(session)
    session.add(_event(c.id, dt.datetime(2026, 8, 5, 9, tzinfo=dt.UTC), 60.0))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(
            c, window="cycles", count=3, today=dt.date(2026, 8, 15)
        )
    assert len(series.points) == 3
    assert series.points[-1].bucket == dt.date(2026, 8, 1)
    assert series.points[-1].value == 1.0


@pytest.mark.asyncio
async def test_windowed_series_keeps_the_contract_unit(engine, app_session_factory, session):
    """A18a.2 — a janela nova não mexe na unidade: crédito continua em reais."""
    t, c = await _seed_windowed(session, contract_type=ContractType.credit_brl)
    session.add(_event(c.id, dt.datetime(2026, 8, 5, 9, tzinfo=dt.UTC), 90.0, 300.0))
    session.add(_event(c.id, dt.datetime(2026, 8, 6, 9, tzinfo=dt.UTC), 45.0, 150.0))
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(
            c, window="months", count=3, today=dt.date(2026, 8, 15)
        )
    assert series.kind == "brl"
    assert series.points[-1].value == 450.0


@pytest.mark.asyncio
async def test_windowed_series_is_empty_for_contracts_without_balance(
    engine, app_session_factory, session
):
    """A18a.4 — SaaS/valor fechado não viram gráfico vazio enganoso."""
    t, c = await _seed_windowed(session, contract_type=ContractType.saas_product)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(
            c, window="months", count=3, today=dt.date(2026, 8, 15)
        )
    assert series.kind == "n/a"
    assert series.points == []


@pytest.mark.asyncio
async def test_series_without_window_keeps_the_old_behaviour(engine, app_session_factory, session):
    """O portal não pode mudar de comportamento por causa do R18a.

    Sem `window`, a série continua sendo a vida inteira do contrato, dia a dia
    (degradando para semana acima de 400 baldes). Regressão explícita.
    """
    t, c = await _seed_windowed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        series = await ContractReadService(s).series(c, today=dt.date(2026, 8, 15))
    assert series.granularity in ("day", "week")
    assert len(series.points) > 3
