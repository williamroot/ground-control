"""D-R aplicado no fechamento — as colunas de teto e validade são lidas.

`domain/carry_over.py` tem a regra testada isolada. Aqui o que se prova é o
elo: que `CycleService.close` de fato lê `carry_over_cap_minutes` e
`carry_over_expires_days` do contrato. Coluna criada e nunca lida é o defeito
mais fácil de cometer nesta onda — foi exatamente o que aconteceu com
`carry_over` antes de a fatura de `hour_bank` deixar de sair zerada.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import Contract, ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus

D = dt.date


async def _seed(session, **kw):
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
        type=ContractType.hour_bank,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        initial_hours=10,
        unit_price_brl=200,
        accumulate_balance_between_cycles=True,
        created_by="seed",
        **kw,
    )
    session.add(c)
    await session.flush()
    await session.commit()
    return t, c


async def _close(s, contract_id, start, end, *, minutes=0.0):
    if minutes:
        await ConsumptionService(s).record(
            RecordConsumption(
                contract_id=contract_id,
                occurred_at=dt.datetime.combine(start, dt.time(9), tzinfo=dt.UTC)
                + dt.timedelta(days=2),
                source_kind="ticket_work",
                source_ref=f"znuny:ticket:{start}",
                billable_minutes=minutes,
                recorded_by="seed",
                znuny_ticket_id=int(start.month),
            )
        )
    cyc = ContractCycle(
        contract_id=contract_id,
        kind=CycleKind.closing,
        period_start=start,
        period_end=end,
        status=CycleStatus.open,
    )
    s.add(cyc)
    await s.flush()
    return await CycleService(s).close(cyc.id)


@pytest.mark.asyncio
async def test_no_cap_and_no_expiry_is_the_previous_behaviour(engine, app_session_factory, session):
    """Regressão: contrato sem as colunas preenchidas acumula como antes."""
    t, c = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _close(s, c.id, D(2026, 1, 1), D(2026, 1, 31))
        totals = await _close(s, c.id, D(2026, 2, 1), D(2026, 2, 28))
    assert totals["carry_in_minutes"] == 600.0  # 10 h do mês anterior
    assert totals["franchise_minutes"] == 1200.0
    assert totals["carry_expired"] == 0.0
    assert totals["carry_capped"] == 0.0


@pytest.mark.asyncio
async def test_the_cap_column_is_read(engine, app_session_factory, session):
    t, c = await _seed(session, carry_over_cap_minutes=300)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _close(s, c.id, D(2026, 1, 1), D(2026, 1, 31))  # sobram 600 min
        totals = await _close(s, c.id, D(2026, 2, 1), D(2026, 2, 28))
    assert totals["carry_in_minutes"] == 300.0, "o teto do contrato foi ignorado"
    assert totals["carry_capped"] == 300.0, "o descarte não ficou registrado"


@pytest.mark.asyncio
async def test_the_expiry_column_is_read(engine, app_session_factory, session):
    """Saldo de janeiro, validade de 30 dias, ciclo de abril: venceu."""
    t, c = await _seed(session, carry_over_expires_days=30)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _close(s, c.id, D(2026, 1, 1), D(2026, 1, 31))
        totals = await _close(s, c.id, D(2026, 4, 1), D(2026, 4, 30))
    assert totals["carry_in_minutes"] == 0.0, "saldo vencido financiou o ciclo novo"
    assert totals["carry_expired"] == 600.0


@pytest.mark.asyncio
async def test_expiry_survives_the_chain_of_cycles(engine, app_session_factory, session):
    """O motivo dos baldes: a cadeia não pode renovar o prazo do saldo velho.

    Janeiro gera 10 h. Fevereiro e março não consomem nada e a franquia deles
    também sobra. Em abril, as 10 h de janeiro venceram — mas as de fevereiro e
    março não. Com um número só, nada teria vencido.
    """
    t, c = await _seed(session, carry_over_expires_days=60)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _close(s, c.id, D(2026, 1, 1), D(2026, 1, 31))
        await _close(s, c.id, D(2026, 2, 1), D(2026, 2, 28))
        await _close(s, c.id, D(2026, 3, 1), D(2026, 3, 31))
        totals = await _close(s, c.id, D(2026, 4, 1), D(2026, 4, 30))
    # 31/01 + 60 dias = 01/04 → ainda válido em 01/04. 10 h + 10 h + 10 h.
    assert totals["carry_in_minutes"] == 1800.0
    assert totals["carry_expired"] == 0.0

    # Um ciclo adiante caem DOIS baldes, não um: 31/01 + 60 = 01/04 e
    # 28/02 + 60 = 29/04 ficaram ambos para trás de 01/05. Sobrevivem março
    # (30/05) e abril (29/06). Cada balde vence pela SUA data — é essa
    # independência que o número único não conseguia representar.
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        totals = await _close(s, c.id, D(2026, 5, 1), D(2026, 5, 31))
    assert totals["carry_expired"] == 1200.0, "os baldes de jan/fev nunca venceram"
    assert totals["carry_in_minutes"] == 1200.0  # mar + abr


@pytest.mark.asyncio
async def test_a_cycle_closed_before_onda5_keeps_its_balance(engine, app_session_factory, session):
    """Ligar a validade não pode apagar o saldo histórico de todo mundo."""
    t, c = await _seed(session, carry_over_expires_days=90)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        old = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=D(2026, 1, 1),
            period_end=D(2026, 1, 31),
            status=CycleStatus.closed,
            totals={"carry_over": 480.0},  # formato antigo: número, sem baldes
        )
        s.add(old)
        await s.flush()
        totals = await _close(s, c.id, D(2026, 2, 1), D(2026, 2, 28))
    assert totals["carry_in_minutes"] == 480.0, "o saldo pré-Onda 5 foi descartado"
