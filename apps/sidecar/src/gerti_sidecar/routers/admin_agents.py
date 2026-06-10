"""Console de tokens/dispositivos do agente de inventário (Spec #1R-a, Task 6).

POST/GET /v1/admin/tenants/{id}/agent-tokens  — cria (token EM CLARO uma vez) / lista
DELETE       /v1/admin/tenants/{id}/agent-tokens/{token_id}  — desabilita (rotação)
GET          /v1/admin/tenants/{id}/devices
POST         /v1/admin/tenants/{id}/devices/{device_id}/approve  (pending→active + CMDB)
POST         /v1/admin/tenants/{id}/devices/{device_id}/revoke

Tudo sob `get_admin_session` (cross-tenant). Escrita abre
`tenant_session_scope(tenant_id, factory=AdminSessionLocal)` (RLS-subject via o
papel BYPASSRLS do console — padrão D16/#1G-a). O plaintext do token NUNCA é
persistido (só sha256); é retornado UMA única vez na criação.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.agent_enroll_service import AgentEnrollService
from gerti_sidecar.domain.agent_secrets import new_enroll_token
from gerti_sidecar.domain.errors import AgentRevoked, EnrollError
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable
from gerti_sidecar.models import AgentEnrollToken, DeviceAgent, Tenant

# GI injetável nos testes (mesmo padrão do router público).
gi = znuny_ticket

router = APIRouter(prefix="/admin", tags=["admin"])


class TokenIn(BaseModel):
    label: str = "instalação"
    max_registrations: int | None = None
    expires_at: str | None = None  # ISO-8601 opcional


class TokenOut(BaseModel):
    id: str
    label: str
    max_registrations: int | None
    registration_count: int
    enabled: bool
    expires_at: str | None
    created_at: str


class TokenCreated(TokenOut):
    token: str  # plaintext, UMA vez
    install_command: str


class DeviceOut(BaseModel):
    id: str
    fingerprint: str
    status: str
    hostname: str
    os: str | None
    znuny_config_item_id: int | None
    specs: dict[str, Any]
    last_seen_at: str | None
    enrolled_at: str | None


def _token_out(t: AgentEnrollToken) -> TokenOut:
    return TokenOut(
        id=str(t.id),
        label=t.label,
        max_registrations=t.max_registrations,
        registration_count=t.registration_count,
        enabled=t.enabled,
        expires_at=t.expires_at.isoformat() if t.expires_at else None,
        created_at=t.created_at.isoformat() if t.created_at else "",
    )


def _device_out(d: DeviceAgent) -> DeviceOut:
    return DeviceOut(
        id=str(d.id),
        fingerprint=d.fingerprint,
        status=d.status,
        hostname=d.hostname,
        os=d.os,
        znuny_config_item_id=d.znuny_config_item_id,
        specs=dict(d.specs or {}),
        last_seen_at=d.last_seen_at.isoformat() if d.last_seen_at else None,
        enrolled_at=d.enrolled_at.isoformat() if d.enrolled_at else None,
    )


def _install_command(token: str) -> str:
    base = get_settings().agent_server_url.rstrip("/")
    return f"curl -fsSL {base}/install.sh | sh -s -- --enroll-token={token} --server={base}"


async def _require_tenant(tenant_id: str) -> uuid.UUID:
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    async with db.AdminSessionLocal() as s:
        found = await s.execute(select(Tenant.id).where(Tenant.id == tid))
        if found.first() is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
    return tid


@router.get("/tenants/{tenant_id}/agent-tokens")
async def list_tokens(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TokenOut]:
    tid = await _require_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rows = (
            (await s.execute(select(AgentEnrollToken).order_by(AgentEnrollToken.created_at.desc())))
            .scalars()
            .all()
        )
        return [_token_out(t) for t in rows]


@router.post("/tenants/{tenant_id}/agent-tokens", status_code=201)
async def create_token(
    tenant_id: str,
    body: TokenIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TokenCreated:
    tid = await _require_tenant(tenant_id)
    plain, digest = new_enroll_token()
    expires = None
    if body.expires_at:
        import datetime as dt

        try:
            expires = dt.datetime.fromisoformat(body.expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_expires_at") from exc
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        tok = AgentEnrollToken(
            tenant_id=tid,
            token_hash=digest,
            label=body.label,
            max_registrations=body.max_registrations,
            expires_at=expires,
        )
        s.add(tok)
        await s.flush()
        out = _token_out(tok)
    return TokenCreated(
        **out.model_dump(),
        token=plain,
        install_command=_install_command(plain),
    )


@router.delete("/tenants/{tenant_id}/agent-tokens/{token_id}")
async def disable_token(
    tenant_id: str,
    token_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TokenOut:
    tid = await _require_tenant(tenant_id)
    try:
        toid = uuid.UUID(token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="token_not_found") from exc
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        tok = (
            await s.execute(select(AgentEnrollToken).where(AgentEnrollToken.id == toid))
        ).scalar_one_or_none()
        if tok is None:
            raise HTTPException(status_code=404, detail="token_not_found")
        tok.enabled = False
        await s.flush()
        return _token_out(tok)


@router.get("/tenants/{tenant_id}/devices")
async def list_devices(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[DeviceOut]:
    tid = await _require_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        rows = (
            (await s.execute(select(DeviceAgent).order_by(DeviceAgent.enrolled_at.desc())))
            .scalars()
            .all()
        )
        return [_device_out(d) for d in rows]


@router.post("/tenants/{tenant_id}/devices/{device_id}/approve")
async def approve_device(
    tenant_id: str,
    device_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> DeviceOut:
    tid = await _require_tenant(tenant_id)
    try:
        did = uuid.UUID(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="device_not_found") from exc
    try:
        async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
            svc = AgentEnrollService(s, gi)
            device = await svc.approve(device_id=did)
            return _device_out(device)
    except AgentRevoked as exc:
        raise HTTPException(status_code=409, detail="device_revoked") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except EnrollError as exc:
        raise HTTPException(status_code=404, detail="device_not_found") from exc


@router.post("/tenants/{tenant_id}/devices/{device_id}/revoke")
async def revoke_device(
    tenant_id: str,
    device_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> DeviceOut:
    tid = await _require_tenant(tenant_id)
    try:
        did = uuid.UUID(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="device_not_found") from exc
    try:
        async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
            svc = AgentEnrollService(s, gi)
            device = await svc.revoke(device_id=did)
            return _device_out(device)
    except EnrollError as exc:
        raise HTTPException(status_code=404, detail="device_not_found") from exc
