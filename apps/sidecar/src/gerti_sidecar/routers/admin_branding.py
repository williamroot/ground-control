"""GET/PUT /v1/admin/tenants/{tid}/branding — console: identidade visual (Spec #3 V4).

Reusa `tenant_branding` (1:1 com o tenant, FORCE RLS) — não cria tabela nova.
Escrita via `tenant_session_scope(tid, factory=AdminSessionLocal)` (mesmo
padrão D16/#1G-a usado em admin_agents/admin_automation). A leitura pública
por host (`GET /v1/branding`, `routers/branding.py`) não é tocada por este
router e continua servindo direto de `tenant_branding`.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain import audit_service
from gerti_sidecar.models import Tenant, TenantBranding

router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_THEMES = ("light", "dark", "system")


class BrandingOut(BaseModel):
    display_name: str
    logo_url: str | None
    primary_color: str
    accent_color: str
    default_theme: str
    support_email: str | None


class BrandingIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    primary_color: str
    accent_color: str
    default_theme: str
    logo_url: str | None = Field(default=None, max_length=500)

    @field_validator("primary_color", "accent_color")
    @classmethod
    def _color_format(cls, v: str) -> str:
        if not _COLOR_RE.match(v):
            raise ValueError("cor deve estar no formato hexadecimal #RRGGBB (ex.: #2563EB)")
        return v

    @field_validator("logo_url")
    @classmethod
    def _logo_https(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not v.startswith("https://"):
            raise ValueError("logo_url precisa começar com https://")
        return v

    @field_validator("default_theme")
    @classmethod
    def _theme_allowed(cls, v: str) -> str:
        if v not in _THEMES:
            raise ValueError(f"default_theme deve ser um de: {', '.join(_THEMES)}")
        return v


async def _resolve_tenant(tenant_id: str) -> uuid.UUID:
    """Valida UUID + existência (cross-tenant, BYPASSRLS) → 404 tenant_not_found."""
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


def _out(row: TenantBranding) -> BrandingOut:
    return BrandingOut(
        display_name=row.display_name,
        logo_url=row.logo_url,
        primary_color=row.primary_color,
        accent_color=row.accent_color,
        default_theme=row.default_theme,
        support_email=row.support_email,
    )


@router.get("/{tenant_id}/branding", response_model=BrandingOut)
async def get_branding(
    tenant_id: str,
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> BrandingOut:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        row = await s.get(TenantBranding, tid)
        if row is None:
            raise HTTPException(status_code=404, detail="branding_not_found")
        return _out(row)


@router.put("/{tenant_id}/branding", response_model=BrandingOut)
async def update_branding(
    tenant_id: str,
    body: BrandingIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> BrandingOut:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid, factory=db.AdminSessionLocal) as s:
        row = await s.get(TenantBranding, tid)
        if row is None:
            row = TenantBranding(tenant_id=tid)
            s.add(row)
        row.display_name = body.display_name
        row.primary_color = body.primary_color
        row.accent_color = body.accent_color
        row.logo_url = body.logo_url
        row.default_theme = body.default_theme
        await s.flush()
        out = _out(row)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="tenant_branding",
        entity_id=str(tid),
        description=f"identidade visual atualizada: {body.display_name}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "display_name": body.display_name,
            "primary_color": body.primary_color,
            "accent_color": body.accent_color,
            "default_theme": body.default_theme,
        },
    )
    return out
