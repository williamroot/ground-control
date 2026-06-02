"""POST /v1/auth/login + /v1/auth/logout — valida no Znuny GI, emite gsid."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.portal_role_service import resolve_role
from gerti_sidecar.integrations.znuny_gi import (
    ZnunyUnavailable,
    authenticate_customer,
)

router = APIRouter(prefix="/auth", tags=["portal"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_resolved")
    try:
        ok = await authenticate_customer(body.username, body.password)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    if not ok:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    # Resolve o papel sob sessão tenant-scoped (RLS). Failure-safe: erro ⇒ helpdesk.
    async with tenant_session_scope(tenant.id) as s:
        role = await resolve_role(s, body.username)
    token = encode_session(str(tenant.id), body.username, role.value, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = 204
    return response
