# apps/sidecar/tests/test_timer_service.py
from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.domain.timer_service import TimerService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import AgentTimer


class _GI:
    def __init__(self):
        self.calls: list = []

    async def time_accounting_add(
        self, *, znuny_ticket_id, agent_login, time_unit, note=None
    ):
        self.calls.append((znuny_ticket_id, agent_login, time_unit, note))


def _t(s: int) -> dt.datetime:
    return dt.datetime(2026, 6, 9, 10, 0, 0, tzinfo=dt.UTC) + dt.timedelta(seconds=s)


@pytest.mark.asyncio
async def test_start_pause_resume_stop(session):
    gi = _GI()
    svc = TimerService(session, gi)
    t = await svc.start(agent_login="will", znuny_ticket_id=19, now=_t(0))
    assert t.status == "running"
    # start de novo é idempotente (mesmo timer)
    t2 = await svc.start(agent_login="will", znuny_ticket_id=19, now=_t(5))
    assert t2.id == t.id
    await svc.pause(t.id, now=_t(30))  # +30s
    t = await session.get(AgentTimer, t.id)
    assert t.status == "paused" and t.accumulated_seconds == 30
    await svc.resume(t.id, now=_t(40))
    # +60s → 90s total = 1.5min
    await svc.stop(t.id, now=_t(100), adjust_minutes=None, note="feito")
    t = await session.get(AgentTimer, t.id)
    assert t.status == "stopped"
    assert gi.calls and gi.calls[0][0] == 19 and gi.calls[0][1] == "will"
    assert abs(float(gi.calls[0][2]) - 1.5) < 1e-6  # 90s = 1.5 min
    assert float(t.committed_time_unit) == 1.5


@pytest.mark.asyncio
async def test_stop_with_adjust_minutes(session):
    gi = _GI()
    svc = TimerService(session, gi)
    t = await svc.start(agent_login="will", znuny_ticket_id=20, now=_t(0))
    await svc.stop(t.id, now=_t(50), adjust_minutes=15.0, note=None)
    assert abs(float(gi.calls[0][2]) - 15.0) < 1e-6  # usa o ajuste, não o real


@pytest.mark.asyncio
async def test_stop_keeps_unstopped_if_gi_fails(session):
    class _BadGI:
        async def time_accounting_add(self, **kw):
            raise znuny_ticket.ZnunyUnavailable("down")

    svc = TimerService(session, _BadGI())
    t = await svc.start(agent_login="will", znuny_ticket_id=21, now=_t(0))
    with pytest.raises(znuny_ticket.ZnunyUnavailable):
        await svc.stop(t.id, now=_t(60), adjust_minutes=None, note=None)
    t = await session.get(AgentTimer, t.id)
    assert t.status != "stopped"  # sem perda: continua ativo p/ re-tentar
