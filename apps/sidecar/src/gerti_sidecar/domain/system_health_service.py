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
from gerti_sidecar.models.sync_cursor import ConsumptionSyncCursor

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


async def _probe_worker() -> dict[str, Any]:
    if db.AdminSessionLocal is None:
        return {"ok": False, "message": "admin_db_unavailable"}
    async with db.AdminSessionLocal() as s:
        last = await s.scalar(select(func.max(ConsumptionSyncCursor.updated_at)))
    if last is None:
        return {"ok": False, "message": "sem sincronização registrada"}
    now = dt.datetime.now(dt.UTC)
    last_utc = last if last.tzinfo is not None else last.replace(tzinfo=dt.UTC)
    lag_seconds = int((now - last_utc).total_seconds())
    return {"ok": True, "last_sync_at": last_utc.isoformat(), "lag_seconds": lag_seconds}


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
        "worker": await _safe(_probe_worker),
        "ai": _probe_ai(settings),
        "asaas": _probe_asaas(settings),
        "version": __version__,
    }
