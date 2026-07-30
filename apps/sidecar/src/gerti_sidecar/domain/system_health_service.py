"""get_system_health — sondas de saúde do sistema (Spec #3 V6).

Cada sonda tem timeout curto (`_PROBE_TIMEOUT` = 3s) e **falha isolada**: uma
sonda vermelha vira `{"ok": false, "message": "..."}` sem derrubar a resposta
— o HTTP do endpoint continua sempre 200. As mensagens de erro são strings
estáticas: NUNCA expõem URL, credencial, token ou senha.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from sqlalchemy import func, select, text

from gerti_sidecar import __version__, db
from gerti_sidecar.config import Settings
from gerti_sidecar.domain.worker_heartbeat import WORKER_CONSUMPTION
from gerti_sidecar.models.sync_cursor import ConsumptionSyncCursor
from gerti_sidecar.models.worker_heartbeat import WorkerHeartbeat

_PROBE_TIMEOUT = 3.0


async def _probe_db() -> dict[str, Any]:
    if db.AdminSessionLocal is None:
        return {"ok": False, "message": "admin_db_unavailable"}
    start = time.monotonic()
    async with db.AdminSessionLocal() as s:
        await s.execute(text("SELECT 1"))
    latency_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "latency_ms": latency_ms}


async def _probe_znuny_gi() -> dict[str, Any]:
    from gerti_sidecar.integrations.znuny_ticket import _resolve_ticket_endpoint

    base, _token = _resolve_ticket_endpoint()
    if not base:
        return {"ok": False, "message": "não configurado"}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            await client.get(base)
    except httpx.HTTPError:
        return {"ok": False, "message": "znuny gi inalcançável"}
    latency_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "latency_ms": latency_ms, "message": "pong"}


def _to_utc(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


async def _probe_worker(settings: Settings) -> dict[str, Any]:
    """Sonda do worker: avaliada pelo HEARTBEAT (prova de vida a cada tick),
    não pelo cursor de sincronização (que só avança quando há trabalho).

    `last_tick_at` = última prova de vida do worker. `last_sync_at` = última
    reconciliação de fato (cursor). Um cursor velho com heartbeat fresco é
    ocioso, não travado — a mensagem tem que dizer isso, não soar como alarme.
    """
    if db.AdminSessionLocal is None:
        return {"ok": False, "message": "admin_db_unavailable"}

    now = dt.datetime.now(dt.UTC)
    threshold_seconds = settings.reconcile_interval_seconds * 3
    async with db.AdminSessionLocal() as s:
        heartbeat = await s.get(WorkerHeartbeat, WORKER_CONSUMPTION)
        last_sync = await s.scalar(select(func.max(ConsumptionSyncCursor.updated_at)))

    last_sync_at = _to_utc(last_sync).isoformat() if last_sync is not None else None

    if heartbeat is None:
        return {
            "ok": False,
            "message": "sem heartbeat registrado — worker pode não ter subido com esta versão",
            "last_sync_at": last_sync_at,
        }

    last_tick_utc = _to_utc(heartbeat.last_tick_at)
    age_seconds = (now - last_tick_utc).total_seconds()
    ok = age_seconds < threshold_seconds

    result: dict[str, Any] = {
        "ok": ok,
        "last_tick_at": last_tick_utc.isoformat(),
        "last_sync_at": last_sync_at,
        "ticks": heartbeat.ticks,
    }
    if heartbeat.last_error:
        result["last_error"] = heartbeat.last_error

    if not ok:
        result["message"] = (
            f"sem sinal de vida há {int(age_seconds)}s "
            f"(esperado a cada {settings.reconcile_interval_seconds}s) — worker pode estar travado"
        )
    else:
        last_sync_utc = _to_utc(last_sync) if last_sync is not None else None
        sync_is_stale = (
            last_sync_utc is None or (now - last_sync_utc).total_seconds() > threshold_seconds
        )
        if sync_is_stale:
            result["message"] = "sem lançamentos novos para processar"

    return result


def _probe_ai(settings: Settings) -> dict[str, Any]:
    if not settings.ai_features_enabled:
        return {"enabled": False}
    return {"enabled": True, "ok": bool(settings.ollama_api_key)}


def _probe_asaas(settings: Settings) -> dict[str, Any]:
    if not settings.asaas_enabled:
        return {"enabled": False}
    return {"enabled": True, "ok": bool(settings.asaas_api_key)}


async def _safe(probe: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Isola uma sonda async: timeout ou qualquer exceção viram `{"ok": false}`."""
    try:
        return await asyncio.wait_for(probe(), timeout=_PROBE_TIMEOUT)
    except Exception:
        return {"ok": False, "message": "sonda indisponível"}


async def get_system_health(settings: Settings) -> dict[str, Any]:
    return {
        "db": await _safe(_probe_db),
        "znuny_gi": await _safe(_probe_znuny_gi),
        "worker": await _safe(lambda: _probe_worker(settings)),
        "ai": _probe_ai(settings),
        "asaas": _probe_asaas(settings),
        "version": __version__,
    }
