"""Onboarding de cliente (Spec #1G-a, ADR D19) — orquestra Znuny + Postgres.

Fluxo de `onboard()` (implementado em T1.C):
  1. GI (via interface de T1.B): CustomerCompany + 1..N CustomerUser + senha.
  2. Postgres CROSS-TENANT via AdminSessionLocal (BYPASSRLS, D16) com tenant_id
     EXPLÍCITO: gerti.tenant + gerti.tenant_branding + gerti.portal_user_role
     (1 por usuário).
Idempotente por `znuny_customer_id` / `subdomain` (reexecução não duplica).

Tipos de domínio CONGELADOS na Fase 0 (T0.2). O router (T1.C) converte o corpo
Pydantic nestes dataclasses; T1.C preenche o corpo de `onboard`.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models.enums import PortalRole
from gerti_sidecar.models.portal_user_role import PortalUserRole
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_branding import TenantBranding


class OnboardingConflict(ValueError):
    """Conflito limpo de onboarding (ex.: subdomínio já em uso por outro cliente)."""


@dataclasses.dataclass(slots=True)
class NewOnboardingUser:
    email: str
    first_name: str
    last_name: str
    password: str
    role: PortalRole = PortalRole.admin


@dataclasses.dataclass(slots=True)
class NewOnboarding:
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    znuny_instance_id: uuid.UUID
    display_name: str
    primary_color: str
    accent_color: str
    support_email: str | None
    logo_url: str | None
    users: list[NewOnboardingUser]
    created_by: str


@dataclasses.dataclass(slots=True)
class OnboardingResult:
    tenant_id: uuid.UUID
    subdomain: str
    created_users: list[str]


class OnboardingService:
    """Cross-tenant: recebe a factory BYPASSRLS (AdminSessionLocal, D16)."""

    def __init__(self, admin_factory: async_sessionmaker[AsyncSession]) -> None:
        self.admin_factory = admin_factory

    async def onboard(self, data: NewOnboarding) -> OnboardingResult:
        # 1. GI (Znuny): empresa + 1..N usuários + senhas. Idempotência do GI é
        #    responsabilidade do GertiAdmin (T1.B); aqui apenas orquestramos.
        await gi.create_customer_company(data.znuny_customer_id, data.trade_name)
        for user in data.users:
            login = user.email
            await gi.create_customer_user(
                login=login,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                customer_id=data.znuny_customer_id,
            )
            await gi.set_password(login, user.password)

        # 2/3. Postgres CROSS-TENANT (BYPASSRLS, D16), check-before-insert.
        async with self.admin_factory() as s:
            async with s.begin():
                tenant = (
                    await s.execute(
                        select(Tenant).where(Tenant.znuny_customer_id == data.znuny_customer_id)
                    )
                ).scalar_one_or_none()

                if tenant is None:
                    # Subdomínio precisa estar livre — se já aponta para OUTRO
                    # cliente, é um conflito limpo (4xx), não uma duplicata.
                    clash = (
                        await s.execute(select(Tenant).where(Tenant.subdomain == data.subdomain))
                    ).scalar_one_or_none()
                    if clash is not None:
                        raise OnboardingConflict(
                            f"subdomain {data.subdomain!r} já em uso por outro cliente"
                        )
                    tenant = Tenant(
                        legal_name=data.legal_name,
                        trade_name=data.trade_name,
                        document=data.document,
                        znuny_customer_id=data.znuny_customer_id,
                        znuny_instance_id=data.znuny_instance_id,
                        subdomain=data.subdomain,
                    )
                    s.add(tenant)
                    await s.flush()
                elif tenant.subdomain != data.subdomain:
                    # Re-onboarding do MESMO cliente, porém apontando para um
                    # subdomínio diferente do já registrado → conflito limpo.
                    raise OnboardingConflict(
                        f"znuny_customer_id {data.znuny_customer_id!r} já registrado "
                        f"com subdomínio {tenant.subdomain!r}"
                    )

                # Branding 1:1 — cria só se ainda não existir.
                branding = await s.get(TenantBranding, tenant.id)
                if branding is None:
                    s.add(
                        TenantBranding(
                            tenant_id=tenant.id,
                            display_name=data.display_name,
                            logo_url=data.logo_url,
                            primary_color=data.primary_color,
                            accent_color=data.accent_color,
                            support_email=data.support_email,
                        )
                    )
                    await s.flush()

                # 1 papel por usuário, idempotente por (tenant_id, lower(login)).
                for user in data.users:
                    login = user.email.lower()
                    existing = (
                        await s.execute(
                            select(PortalUserRole).where(
                                PortalUserRole.tenant_id == tenant.id,
                                func.lower(PortalUserRole.customer_login) == login,
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        s.add(
                            PortalUserRole(
                                tenant_id=tenant.id,
                                customer_login=login,
                                role=user.role,
                            )
                        )
                        await s.flush()

                tenant_id = tenant.id

        return OnboardingResult(
            tenant_id=tenant_id,
            subdomain=data.subdomain,
            created_users=[u.email.lower() for u in data.users],
        )
