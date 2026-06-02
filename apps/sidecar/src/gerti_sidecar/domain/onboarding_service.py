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

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.models.enums import PortalRole


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
        raise NotImplementedError("T1.C: orquestra GI + tenant/branding/papéis (ADR D19)")
