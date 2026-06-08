from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.jobs import worker


@pytest.mark.asyncio
async def test_tick_calls_reconcile_and_daily_close(monkeypatch):
    calls = {"reconcile": 0, "close": 0}

    class FakeRecon:
        def __init__(self, gi): pass

        async def reconcile(self):
            calls["reconcile"] += 1
            return 0

    class FakeCloser:
        async def close_due_cycles(self):
            calls["close"] += 1
            return 0

    monkeypatch.setattr(worker, "ReconciliationService", FakeRecon)
    monkeypatch.setattr(worker, "CycleCloser", FakeCloser)

    state = worker.WorkerState(last_close_date=None)
    # primeira tick: reconcilia + fecha (novo dia)
    await worker.tick(state, today=dt.date(2026, 6, 8))
    assert calls == {"reconcile": 1, "close": 1}
    assert state.last_close_date == dt.date(2026, 6, 8)
    # segunda tick no mesmo dia: só reconcilia
    await worker.tick(state, today=dt.date(2026, 6, 8))
    assert calls == {"reconcile": 2, "close": 1}
