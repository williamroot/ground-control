"""Sessão de portal: JWT HS256 assinado + dependency anti cross-tenant.

Payload: {tenant_id (str), customer_login (str), role (str), exp (int posix utc)}.
get_current_session: 401 se sem tenant / cookie ausente|inválido|expirado;
403 se o tenant do cookie != tenant do subdomínio (request.state.tenant).
require_admin: 403 se o papel da sessão não for admin (Spec #1H).
"""

from __future__ import annotations

import datetime as dt
from typing import TypedDict

import jwt
from fastapi import Depends, HTTPException, Request

from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.models.enums import PortalRole

_ALG = "HS256"


class SessionPayload(TypedDict):
    tenant_id: str
    customer_login: str
    role: str
    exp: int


def encode_session(tenant_id: str, customer_login: str, role: str, settings: Settings) -> str:
    exp = int(
        (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=settings.session_ttl_seconds)).timestamp()
    )
    payload: SessionPayload = {
        "tenant_id": tenant_id,
        "customer_login": customer_login,
        "role": role,
        "exp": exp,
    }
    return jwt.encode(dict(payload), settings.session_secret, algorithm=_ALG)


def decode_session(token: str, settings: Settings) -> SessionPayload | None:
    try:
        data = jwt.decode(token, settings.session_secret, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    if not isinstance(data.get("tenant_id"), str) or not isinstance(
        data.get("customer_login"), str
    ):
        return None
    # Token sem `role` (emitido antes do #1H, TTL em trânsito) ⇒ least-privilege.
    role = data.get("role")
    if role not in (PortalRole.admin.value, PortalRole.helpdesk.value):
        role = PortalRole.helpdesk.value
    return SessionPayload(
        tenant_id=data["tenant_id"],
        customer_login=data["customer_login"],
        role=role,
        exp=int(data["exp"]),
    )


async def get_current_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SessionPayload:
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(status_code=401, detail="no_session")
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="no_session")
    payload = decode_session(token, settings)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid_session")
    if payload["tenant_id"] != str(tenant.id):
        raise HTTPException(status_code=403, detail="tenant_mismatch")
    return payload


async def require_admin(
    session: SessionPayload = Depends(get_current_session),
) -> SessionPayload:
    """Exige papel admin (Spec #1H): 403 forbidden_role para help-desk.

    Compõe sobre get_current_session (que já garante 401 sem sessão e 403
    cross-tenant). Usada como dependency de rota nos endpoints de contrato/
    dashboard (dados + valores financeiros — admin-only).
    """
    if session["role"] != PortalRole.admin.value:
        raise HTTPException(status_code=403, detail="forbidden_role")
    return session
