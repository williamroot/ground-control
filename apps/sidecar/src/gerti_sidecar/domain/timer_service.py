# apps/sidecar/src/gerti_sidecar/domain/timer_service.py
"""Cronômetro do agente (Spec #1J): start/pause/resume/stop + cálculo de tempo.

Opera sob a sessão admin (BYPASSRLS — o agente é cross-tenant). pause/resume só
acumulam; stop calcula o total, lança em time_accounting via GI (com ajuste
opcional) e SÓ então marca stopped (sem perda nem relançamento). `now` é
injetável p/ testes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import AgentTimer


class TimerError(Exception):
    """Estado inválido do timer (->409/404)."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _round_minutes(seconds: float) -> float:
    m = Decimal(seconds) / Decimal(60)
    return float(m.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class TimerService:
    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self._session = session
        self._gi = gi

    async def start(self, *, agent_login: str, znuny_ticket_id: int,
                    now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        existing = (
            await self._session.execute(
                select(AgentTimer).where(
                    AgentTimer.agent_login == agent_login,
                    AgentTimer.znuny_ticket_id == znuny_ticket_id,
                    AgentTimer.status != "stopped",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing  # idempotente
        t = AgentTimer(
            agent_login=agent_login, znuny_ticket_id=znuny_ticket_id,
            status="running", accumulated_seconds=0, last_started_at=now,
        )
        self._session.add(t)
        await self._session.flush()
        return t

    async def _get(self, timer_id: uuid.UUID) -> AgentTimer:
        t = await self._session.get(AgentTimer, timer_id)
        if t is None:
            raise TimerError("timer inexistente")
        return t

    async def pause(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "running" and t.last_started_at is not None:
            t.accumulated_seconds += int((now - t.last_started_at).total_seconds())
        t.status = "paused"
        t.last_started_at = None
        t.updated_at = now
        await self._session.flush()
        return t

    async def resume(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "stopped":
            raise TimerError("timer já encerrado")
        t.status = "running"
        t.last_started_at = now
        t.updated_at = now
        await self._session.flush()
        return t

    async def stop(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None,
                   adjust_minutes: float | None = None, note: str | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "stopped":
            raise TimerError("timer já encerrado")
        total = t.accumulated_seconds
        if t.status == "running" and t.last_started_at is not None:
            total += int((now - t.last_started_at).total_seconds())
        minutes = adjust_minutes if adjust_minutes is not None else _round_minutes(total)
        if minutes <= 0:
            minutes = 0.01  # nunca lança 0 (TimeAccountingAdd exige > 0)
        # Lança no Znuny PRIMEIRO; só marca stopped se o GI confirmar.
        await self._gi.time_accounting_add(
            znuny_ticket_id=t.znuny_ticket_id, agent_login=t.agent_login,
            time_unit=float(minutes), note=note,
        )
        t.accumulated_seconds = total
        t.status = "stopped"
        t.last_started_at = None
        t.note = note
        t.committed_time_unit = Decimal(str(minutes))
        t.updated_at = now
        await self._session.flush()
        return t
