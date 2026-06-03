"""/v1/admin/tenants* — listar, onboarding e detalhe de cliente (Spec #1G-a).

ADR D19. Todos exigem `get_admin_session` (401 sem sessão admin). Contratos
Pydantic CONGELADOS na Fase 0; T1.C preenche o corpo (orquestra GI +
gerti.tenant/branding/portal_user_role via AdminSessionLocal, D16).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain.onboarding_service import (
    NewOnboarding,
    NewOnboardingUser,
    OnboardingConflict,
    OnboardingService,
)
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models.contract import Contract
from gerti_sidecar.models.enums import PortalRole
from gerti_sidecar.models.portal_user_role import PortalUserRole
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_branding import TenantBranding
from gerti_sidecar.models.znuny_instance import ZnunyInstance

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


def _require_admin_factory() -> None:
    """Garante que a factory BYPASSRLS (AdminSessionLocal, D16) está disponível."""
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")


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
def _parse_tenant_id(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


async def _build_detail(s: AsyncSession, tenant: Tenant) -> TenantDetail:
    branding = await s.get(TenantBranding, tenant.id)
    users = (
        (
            await s.execute(
                select(PortalUserRole)
                .where(PortalUserRole.tenant_id == tenant.id)
                .order_by(PortalUserRole.customer_login)
            )
        )
        .scalars()
        .all()
    )
    contracts = (
        (
            await s.execute(
                select(Contract).where(Contract.tenant_id == tenant.id).order_by(Contract.code)
            )
        )
        .scalars()
        .all()
    )
    return TenantDetail(
        id=str(tenant.id),
        legal_name=tenant.legal_name,
        trade_name=tenant.trade_name,
        document=tenant.document,
        subdomain=tenant.subdomain,
        znuny_customer_id=tenant.znuny_customer_id,
        status=tenant.status,
        branding=(
            BrandingIn(
                display_name=branding.display_name,
                primary_color=branding.primary_color,
                accent_color=branding.accent_color,
                support_email=branding.support_email,
                logo_url=branding.logo_url,
            )
            if branding is not None
            else None
        ),
        users=[TenantUserOut(customer_login=u.customer_login, role=u.role.value) for u in users],
        contracts=[
            TenantContractOut(id=str(c.id), code=c.code, type=c.type.value, status=c.status.value)
            for c in contracts
        ],
    )


@router.get("")
async def list_tenants(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TenantSummary]:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    async with db.AdminSessionLocal() as s:
        count_sq = (
            select(Contract.tenant_id, func.count().label("n"))
            .group_by(Contract.tenant_id)
            .subquery()
        )
        rows = (
            await s.execute(
                select(Tenant, func.coalesce(count_sq.c.n, 0))
                .outerjoin(count_sq, count_sq.c.tenant_id == Tenant.id)
                .order_by(Tenant.trade_name)
            )
        ).all()
    return [
        TenantSummary(
            id=str(t.id),
            trade_name=t.trade_name,
            subdomain=t.subdomain,
            contract_count=int(n),
            status=t.status,
        )
        for t, n in rows
    ]


@router.post("", status_code=201)
async def onboard_tenant(
    body: NewTenantBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> OnboardingResultOut:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None

    # znuny_instance_id: §2.1 garante exatamente 1 Znuny. Resolvemos a única
    # linha; se houver mais de uma, escolhemos deterministicamente a mais antiga
    # (menor created_at) para manter o comportamento previsível.
    async with db.AdminSessionLocal() as s:
        instance = (
            await s.execute(select(ZnunyInstance).order_by(ZnunyInstance.created_at).limit(1))
        ).scalar_one_or_none()
    if instance is None:
        raise HTTPException(status_code=503, detail="no_znuny_instance")

    new = NewOnboarding(
        legal_name=body.legal_name,
        trade_name=body.trade_name,
        document=body.document,
        subdomain=body.subdomain,
        znuny_customer_id=body.znuny_customer_id,
        znuny_instance_id=instance.id,
        display_name=body.branding.display_name,
        primary_color=body.branding.primary_color,
        accent_color=body.branding.accent_color,
        support_email=body.branding.support_email,
        logo_url=body.branding.logo_url,
        users=[
            NewOnboardingUser(
                email=u.email,
                first_name=u.first_name,
                last_name=u.last_name,
                password=u.password,
                role=PortalRole(u.role),
            )
            for u in body.users
        ],
        created_by=admin["agent_login"],
    )

    service = OnboardingService(db.AdminSessionLocal)
    try:
        result = await service.onboard(new)
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except gi.ZnunyWriteError as exc:
        raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc
    except OnboardingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, result.tenant_id)
        assert tenant is not None
        detail = await _build_detail(s, tenant)

    return OnboardingResultOut(
        tenant=detail,
        subdomain_to_register=result.subdomain,
        created_users=result.created_users,
    )


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantDetail:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)
    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        return await _build_detail(s, tenant)


@router.post("/{tenant_id}/users", status_code=201)
async def add_tenant_user(
    tenant_id: str,
    body: OnboardingUserIn,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantUserOut:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)
    login = body.email.lower()

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        customer_id = tenant.znuny_customer_id

    # GI: cria o customer_user + senha no Znuny.
    try:
        await gi.create_customer_user(
            login=body.email,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            customer_id=customer_id,
        )
        await gi.set_password(body.email, body.password)
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except gi.ZnunyWriteError as exc:
        raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc

    role = PortalRole(body.role)
    async with db.AdminSessionLocal() as s:
        async with s.begin():
            existing = (
                await s.execute(
                    select(PortalUserRole).where(
                        PortalUserRole.tenant_id == tid,
                        func.lower(PortalUserRole.customer_login) == login,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(PortalUserRole(tenant_id=tid, customer_login=login, role=role))

    return TenantUserOut(customer_login=login, role=role.value)
