"""GET /v1/me — sessão válida; devolve identidade + display_name do tenant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.models import TenantBranding

router = APIRouter(prefix="/me", tags=["portal"])


class MeResponse(BaseModel):
    tenant_id: str
    display_name: str
    customer_login: str
    role: str


@router.get("", response_model=MeResponse)
async def get_me(
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> MeResponse:
    row = (await session.execute(select(TenantBranding))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="branding_not_found")
    return MeResponse(
        tenant_id=session_payload["tenant_id"],
        display_name=row.display_name,
        customer_login=session_payload["customer_login"],
        role=session_payload["role"],
    )
