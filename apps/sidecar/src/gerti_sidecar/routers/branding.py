"""GET /v1/branding — não autenticado, escopado por subdomínio (RLS).

TenantMiddleware já setou request.state.tenant + app.current_tenant a
partir do subdomínio. Host sem subdomínio -> sem tenant -> 404 limpo
(Nuxt aplica tema default). Payload mínimo, sem dado sensível.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.models import TenantBranding

router = APIRouter(prefix="/branding", tags=["portal"])


class BrandingResponse(BaseModel):
    display_name: str
    logo_url: str | None
    primary_color: str
    accent_color: str
    default_theme: str
    support_email: str | None


def _require_tenant(request: Request) -> None:
    if getattr(request.state, "tenant", None) is None:
        raise HTTPException(status_code=404, detail="tenant_not_resolved")


@router.get("", response_model=BrandingResponse)
async def get_branding(
    request: Request,
    _: None = Depends(_require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> BrandingResponse:
    row = (await session.execute(select(TenantBranding))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="branding_not_found")
    return BrandingResponse(
        display_name=row.display_name,
        logo_url=row.logo_url,
        primary_color=row.primary_color,
        accent_color=row.accent_color,
        default_theme=row.default_theme,
        support_email=row.support_email,
    )
