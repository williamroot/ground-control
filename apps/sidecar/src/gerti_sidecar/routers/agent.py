"""Endpoints públicos do agente de inventário (Spec #1R-a) — /v1/agent/*.

Sem dependência de sessão de cookie: a autenticação é o **Bearer** do agente
(enroll token no enroll; agent_secret no heartbeat), guardado hasheado at-rest.
O tenant NÃO vem do subdomínio — `/v1/agent` está na allowlist do TenantMiddleware
(como `/v1/hooks`/`/v1/admin`). O tenant é resolvido server-side a partir do TOKEN:

1. lookup BYPASSRLS de `agent_enroll_token` por sha256 → `tenant_id` (no enroll) ou
   de `device_agent` por sha256(agent_secret) → `tenant_id` (no heartbeat);
2. a escrita roda dentro de `tenant_session_scope(tenant_id, factory=AdminSessionLocal)`
   (RLS-subject) → o `customer_id` do CMDB sai SEMPRE do tenant dono do token.

Mapeamento de erros: EnrollTokenInvalid/AgentRevoked → 401; guardrail (pending) →
202; ZnunyUnavailable → 503.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.agent_enroll_service import AgentEnrollService
from gerti_sidecar.domain.agent_secrets import hash_token
from gerti_sidecar.domain.errors import AgentRevoked, EnrollError, EnrollTokenInvalid
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable
from gerti_sidecar.models import AgentEnrollToken, DeviceAgent

# Módulo do GI injetável nos testes (mesmo padrão de hooks/timer).
gi = znuny_ticket

router = APIRouter(prefix="/agent", tags=["agent"])

HEARTBEAT_INTERVAL_SECONDS = 3600


class EnrollBody(BaseModel):
    fingerprint: str
    hostname: str
    os: str | None = None
    specs: dict[str, Any] = {}


class HeartbeatBody(BaseModel):
    specs: dict[str, Any] = {}
    uptime_seconds: int | None = None


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing_bearer")
    return token


def _admin_factory():
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


async def _tenant_for_token(token: str) -> uuid.UUID:
    """Resolve o tenant dono do enroll token (lookup BYPASSRLS, é diretório)."""
    factory = _admin_factory()
    async with factory() as s:
        tid = (
            await s.execute(
                select(AgentEnrollToken.tenant_id).where(
                    AgentEnrollToken.token_hash == hash_token(token)
                )
            )
        ).scalar_one_or_none()
    if tid is None:
        raise HTTPException(status_code=401, detail="invalid_enroll_token")
    return tid


async def _tenant_for_secret(secret: str) -> uuid.UUID:
    """Resolve o tenant dono do device pelo agent_secret (lookup BYPASSRLS)."""
    factory = _admin_factory()
    async with factory() as s:
        tid = (
            await s.execute(
                select(DeviceAgent.tenant_id).where(
                    DeviceAgent.agent_secret_hash == hash_token(secret)
                )
            )
        ).scalar_one_or_none()
    if tid is None:
        raise HTTPException(status_code=401, detail="invalid_agent_secret")
    return tid


@router.post("/enroll")
async def enroll(
    body: EnrollBody,
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _bearer(authorization)
    tid = await _tenant_for_token(token)
    try:
        async with tenant_session_scope(tid, factory=_admin_factory()) as s:
            svc = AgentEnrollService(s, gi)
            device, secret = await svc.enroll(
                token=token,
                fingerprint=body.fingerprint,
                hostname=body.hostname,
                os=body.os,
                specs=body.specs,
            )
            result = {
                "agent_id": str(device.id),
                "agent_secret": secret,
                "status": device.status,
                "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            }
    except EnrollTokenInvalid as exc:
        raise HTTPException(status_code=401, detail="invalid_enroll_token") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except EnrollError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # active → 201; pending (sobre limite/expirado) → 202 (sem CMDB).
    response.status_code = 202 if result["status"] == "pending" else 201
    return result


@router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    secret = _bearer(authorization)
    tid = await _tenant_for_secret(secret)
    try:
        async with tenant_session_scope(tid, factory=_admin_factory()) as s:
            svc = AgentEnrollService(s, gi)
            device = await svc.heartbeat(agent_secret=secret, specs=body.specs)
            return {
                "ok": True,
                "status": device.status,
                "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            }
    except AgentRevoked as exc:
        raise HTTPException(status_code=401, detail="agent_revoked") from exc
    except EnrollTokenInvalid as exc:
        raise HTTPException(status_code=401, detail="invalid_agent_secret") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
