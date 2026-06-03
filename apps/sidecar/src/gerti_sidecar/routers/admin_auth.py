"""POST /v1/admin/auth/login|logout — auth de agente Znuny, emite gsid_adm.

Spec #1G-a / ADR D19. Contrato Pydantic CONGELADO na Fase 0; T1.A preenche o
corpo (valida no GI via `authenticate_agent`, emite o cookie `gsid_adm`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.integrations.znuny_agent_auth import (
    ZnunyUnavailable,
    authenticate_agent,
)

router = APIRouter(prefix="/admin/auth", tags=["admin"])


class AdminLoginBody(BaseModel):
    login: str
    password: str


@router.post("/login")
async def admin_login(
    body: AdminLoginBody,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    try:
        ok = await authenticate_agent(body.login, body.password)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    if not ok:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token = encode_admin_session(body.login, settings)
    response.set_cookie(
        key=settings.admin_session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@router.post("/logout", status_code=204)
async def admin_logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    response.delete_cookie(
        key=settings.admin_session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = 204
    return response
