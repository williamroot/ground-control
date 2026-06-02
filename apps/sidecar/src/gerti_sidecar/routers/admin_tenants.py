"""/v1/admin/tenants* — listar, onboarding e detalhe de cliente (Spec #1G-a).

ADR D19. Todos exigem `get_admin_session` (401 sem sessão admin). Contratos
Pydantic CONGELADOS na Fase 0; T1.C preenche o corpo (orquestra GI +
gerti.tenant/branding/portal_user_role via AdminSessionLocal, D16).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


# ── entrada ──────────────────────────────────────────────────────────────
class OnboardingUserIn(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: str
    role: Literal["admin", "helpdesk"] = "admin"


class BrandingIn(BaseModel):
    display_name: str
    primary_color: str = "#2563EB"
    accent_color: str = "#1E40AF"
    support_email: str | None = None
    logo_url: str | None = None


class NewTenantBody(BaseModel):
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    branding: BrandingIn
    users: list[OnboardingUserIn] = Field(min_length=1)


# ── saída ────────────────────────────────────────────────────────────────
class TenantSummary(BaseModel):
    id: str
    trade_name: str
    subdomain: str
    contract_count: int
    status: str


class TenantUserOut(BaseModel):
    customer_login: str
    role: str


class TenantContractOut(BaseModel):
    id: str
    code: str
    type: str
    status: str


class TenantDetail(BaseModel):
    id: str
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    status: str
    branding: BrandingIn | None
    users: list[TenantUserOut]
    contracts: list[TenantContractOut]


class OnboardingResultOut(BaseModel):
    tenant: TenantDetail
    subdomain_to_register: str
    created_users: list[str]


# ── endpoints (stubs 501 — T1.C) ──────────────────────────────────────────
@router.get("")
async def list_tenants(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TenantSummary]:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.C


@router.post("", status_code=201)
async def onboard_tenant(
    body: NewTenantBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> OnboardingResultOut:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.C


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantDetail:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.C


@router.post("/{tenant_id}/users", status_code=201)
async def add_tenant_user(
    tenant_id: str,
    body: OnboardingUserIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantUserOut:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.C
