"""Heartbeat do worker (Spec #3) — prova de vida separada do cursor de sync.

`consumption_sync_cursor.updated_at` só avança quando há trabalho: um worker
vivo e ocioso fica indistinguível de um travado se a sonda olhar só pra ele.
`worker_heartbeat` é gravado a CADA tick — com trabalho ou sem, sucesso ou
falha — e é isso que a sonda de saúde passa a usar.

Cobre: heartbeat gravado a cada tick mesmo sem trabalho; falha ao gravar
heartbeat não derruba o loop; sonda ok com heartbeat fresco + cursor antigo
(caso ocioso — o bug que este spec conserta); sonda not ok com heartbeat
velho; sonda not ok quando não há heartbeat.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import Settings
from gerti_sidecar.domain.system_health_service import get_system_health
from gerti_sidecar.domain.worker_heartbeat import WORKER_CONSUMPTION, record_heartbeat
from gerti_sidecar.jobs import worker
from gerti_sidecar.models.sync_cursor import ConsumptionSyncCursor
from gerti_sidecar.models.worker_heartbeat import WorkerHeartbeat
from gerti_sidecar.models.znuny_instance import ZnunyInstance


def _wire(monkeypatch, engine) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    return factory


def _settings(db_url: str, *, reconcile_interval_seconds: int = 60) -> Settings:
    return Settings(database_url=db_url, reconcile_interval_seconds=reconcile_interval_seconds)


# --- record_heartbeat --------------------------------------------------


@pytest.mark.asyncio
async def test_record_heartbeat_creates_row_and_increments_on_upsert(engine, monkeypatch):
    _wire(monkeypatch, engine)

    await record_heartbeat(WORKER_CONSUMPTION, error=None)
    async with db.AdminSessionLocal() as s:
        hb = await s.get(WorkerHeartbeat, WORKER_CONSUMPTION)
    assert hb is not None
    assert hb.ticks == 1
    assert hb.last_error is None
    assert hb.last_success_at is not None

    await record_heartbeat(WORKER_CONSUMPTION, error="boom")
    async with db.AdminSessionLocal() as s:
        hb = await s.get(WorkerHeartbeat, WORKER_CONSUMPTION)
    assert hb is not None
    assert hb.ticks == 2
    assert hb.last_error == "boom"
    stale_success_at = hb.last_success_at

    # tick seguinte volta a passar: last_error limpa, last_success_at avança.
    await record_heartbeat(WORKER_CONSUMPTION, error=None)
    async with db.AdminSessionLocal() as s:
        hb = await s.get(WorkerHeartbeat, WORKER_CONSUMPTION)
    assert hb is not None
    assert hb.ticks == 3
    assert hb.last_error is None
    assert hb.last_success_at is not None
    assert hb.last_success_at >= stale_success_at


# --- worker.tick ---------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_records_heartbeat_even_without_work(engine, monkeypatch):
    """Iteração sem nada a reconciliar ainda grava heartbeat (prova de vida)."""
    _wire(monkeypatch, engine)

    class FakeRecon:
        def __init__(self, gi):
            pass

        async def reconcile(self):
            return 0

    class FakeCloser:
        async def close_due_cycles(self):
            return 0

    class FakeOverdue:
        async def mark_overdue_due(self):
            return 0

    monkeypatch.setattr(worker, "ReconciliationService", FakeRecon)
    monkeypatch.setattr(worker, "CycleCloser", FakeCloser)
    monkeypatch.setattr(worker, "InvoiceOverdueMarker", FakeOverdue)

    state = worker.WorkerState(last_close_date=dt.date(2026, 6, 9))
    await worker.tick(state, today=dt.date(2026, 6, 9))

    async with db.AdminSessionLocal() as s:
        hb = await s.get(WorkerHeartbeat, WORKER_CONSUMPTION)
    assert hb is not None
    assert hb.ticks == 1
    assert hb.last_error is None


@pytest.mark.asyncio
async def test_tick_heartbeat_write_failure_does_not_crash_loop(monkeypatch):
    """AdminSessionLocal ausente -> record_heartbeat levanta, mas tick() segue."""
    monkeypatch.setattr(db, "AdminSessionLocal", None)

    class FakeRecon:
        def __init__(self, gi):
            pass

        async def reconcile(self):
            return 0

    monkeypatch.setattr(worker, "ReconciliationService", FakeRecon)

    state = worker.WorkerState(last_close_date=dt.date(2026, 6, 9))
    # Mesmo dia de last_close_date: pula close/overdue, isola o teste no heartbeat.
    await worker.tick(state, today=dt.date(2026, 6, 9))  # não deve levantar


# --- sonda de saúde (worker via get_system_health) -----------------------


@pytest.mark.asyncio
async def test_probe_worker_not_ok_when_no_heartbeat_registered(engine, db_url, monkeypatch):
    _wire(monkeypatch, engine)
    health = await get_system_health(_settings(db_url))
    result = health["worker"]
    assert result["ok"] is False
    assert "heartbeat" in result["message"].lower()


@pytest.mark.asyncio
async def test_probe_worker_not_ok_when_heartbeat_stale(engine, db_url, monkeypatch):
    factory = _wire(monkeypatch, engine)
    now = dt.datetime.now(dt.UTC)
    async with factory() as s:
        s.add(
            WorkerHeartbeat(
                worker=WORKER_CONSUMPTION,
                last_tick_at=now - dt.timedelta(seconds=500),
                last_success_at=now - dt.timedelta(seconds=500),
                ticks=10,
            )
        )
        await s.commit()

    health = await get_system_health(_settings(db_url, reconcile_interval_seconds=60))
    result = health["worker"]
    assert result["ok"] is False
    assert "sem sinal de vida" in result["message"].lower()


@pytest.mark.asyncio
async def test_probe_worker_ok_when_heartbeat_fresh_even_with_stale_cursor(
    engine, db_url, monkeypatch
):
    """Caso ocioso (o bug consertado): heartbeat de agora, cursor de 35 dias
    atrás — tem que reportar ok:true com mensagem de ociosidade, não de atraso."""
    factory = _wire(monkeypatch, engine)
    now = dt.datetime.now(dt.UTC)
    async with factory() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        s.add(
            ConsumptionSyncCursor(
                znuny_instance_id=inst.id,
                last_time_accounting_id=49,
                updated_at=now - dt.timedelta(days=35),
            )
        )
        s.add(
            WorkerHeartbeat(
                worker=WORKER_CONSUMPTION,
                last_tick_at=now,
                last_success_at=now,
                ticks=1000,
            )
        )
        await s.commit()

    health = await get_system_health(_settings(db_url, reconcile_interval_seconds=60))
    result = health["worker"]
    assert result["ok"] is True
    assert result["last_tick_at"]
    assert result["last_sync_at"]
    assert "sem lançamentos novos para processar" in result["message"]
