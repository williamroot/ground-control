"""GET /v1/admin/system/health — console: saúde do sistema (Spec #3 V6).

Sondas com falha isolada (`domain/system_health_service.get_system_health`):
uma sonda vermelha vira `{"ok": false, "message": "..."}` — o HTTP desta
rota é sempre 200. Nunca expõe URL/credencial/token/senha.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.domain.system_health_service import get_system_health

router = APIRouter(prefix="/admin/system", tags=["admin"])


@router.get("/health")
async def system_health(
    _admin: AdminSessionPayload = Depends(get_admin_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await get_system_health(settings)
