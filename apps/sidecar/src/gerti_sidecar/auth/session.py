"""Sessão de portal: JWT HS256 assinado + dependency anti cross-tenant.

Payload: {tenant_id (str), customer_login (str), exp (int posix utc)}.
get_current_session: 401 se sem tenant / cookie ausente|inválido|expirado;
403 se o tenant do cookie != tenant do subdomínio (request.state.tenant).
"""

from __future__ import annotations

import datetime as dt
from typing import TypedDict

import jwt
from fastapi import Depends, HTTPException, Request

from gerti_sidecar.config import Settings, get_settings

_ALG = "HS256"


class SessionPayload(TypedDict):
    tenant_id: str
    customer_login: str
    exp: int


def encode_session(tenant_id: str, customer_login: str, settings: Settings) -> str:
    exp = int(
        (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=settings.session_ttl_seconds)).timestamp()
    )
    payload: SessionPayload = {
        "tenant_id": tenant_id,
        "customer_login": customer_login,
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
    return SessionPayload(
        tenant_id=data["tenant_id"],
        customer_login=data["customer_login"],
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
