"""Provisionamento pós-pagamento (Spec #2).

Modelo confirmado: pré-cadastro → paga → webhook provisiona. Ao confirmar o
pagamento, reusa OnboardingService (#1G) p/ criar tenant+usuários no Znuny+Postgres
e ContractService (#1C) p/ criar o contrato do plano. Idempotente: uma sessão já
`provisioned` não reprovisiona. Cross-tenant via AdminSessionLocal (BYPASSRLS).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.errors import ProvisioningError
from gerti_sidecar.domain.onboarding_service import (
    NewOnboarding,
    NewOnboardingUser,
    OnboardingService,
)
from gerti_sidecar.models.contratacao import CheckoutSession, Payment, Plan
from gerti_sidecar.models.enums import ContractType, PortalRole
from gerti_sidecar.models.znuny_instance import ZnunyInstance


def _factory() -> async_sessionmaker[AsyncSession]:
    if db.AdminSessionLocal is None:
        raise ProvisioningError("admin_db_unavailable")
    return db.AdminSessionLocal


def _plan_to_new_contract(plan: Plan, *, created_by: str, today: dt.date) -> NewContract:
    """Mapeia um Plan para os campos de NewContract conforme o tipo."""
    ctype = ContractType(plan.contract_type)
    unit_price = (plan.unit_price_cents / 100) if plan.unit_price_cents is not None else None
    code = f"{plan.slug.upper()}-{today.year}"
    # 1 ano de vigência; trata 29/02 (ano destino não-bissexto) caindo p/ 28/02.
    try:
        ends_on = today.replace(year=today.year + 1)
    except ValueError:
        ends_on = today.replace(year=today.year + 1, day=28)
    return NewContract(
        code=code,
        type=ctype,
        starts_on=today,
        ends_on=ends_on,
        created_by=created_by,
        initial_amount_brl=float(plan.initial_amount_brl)
        if plan.initial_amount_brl is not None
        else None,
        initial_hours=float(plan.initial_hours) if plan.initial_hours is not None else None,
        initial_service_count=plan.initial_service_count,
        unit_price_brl=unit_price,
        billing_period_months=plan.billing_period_months,
        closing_period_months=plan.closing_period_months,
    )


class ProvisioningService:
    def __init__(self) -> None:
        self._factory = _factory()

    async def provision(
        self, session_id: uuid.UUID, *, now: dt.datetime | None = None
    ) -> uuid.UUID:
        """Provisiona a contratação de uma checkout_session paga. Idempotente."""
        now = now or dt.datetime.now(dt.UTC)
        async with self._factory() as s:
            cs = await s.get(CheckoutSession, session_id)
            if cs is None:
                raise ProvisioningError(f"checkout_session {session_id} inexistente")
            if cs.status == "provisioned" and cs.provisioned_tenant_id is not None:
                return cs.provisioned_tenant_id  # idempotente
            plan = await s.get(Plan, cs.plan_id)
            if plan is None:
                raise ProvisioningError("plano inexistente")
            applicant = cast(dict[str, Any], cs.applicant)

        tenant_id = cs.target_tenant_id
        if tenant_id is None:
            tenant_id = await self._onboard(applicant)

        # contrato (RLS-subject sob o tenant recém-criado, factory BYPASSRLS p/ o GUC)

        async with tenant_session_scope(tenant_id, factory=self._factory) as ts:
            svc = ContractService(ts)
            await svc.create(_plan_to_new_contract(plan, created_by="checkout", today=now.date()))

        # finaliza a sessão + vincula o pagamento; limpa a senha do applicant (at-rest)
        async with self._factory() as s:
            async with s.begin():
                cs = await s.get(CheckoutSession, session_id, with_for_update=True)
                assert cs is not None
                cs.status = "provisioned"
                cs.provisioned_tenant_id = tenant_id
                cs.updated_at = now
                appl = dict(cast(dict[str, Any], cs.applicant))
                if isinstance(appl.get("admin"), dict):
                    appl["admin"] = {k: v for k, v in appl["admin"].items() if k != "password"}
                    cs.applicant = appl
                pay = (
                    (
                        await s.execute(
                            select(Payment).where(Payment.checkout_session_id == session_id)
                        )
                    )
                    .scalars()
                    .first()
                )
                if pay is not None:
                    pay.tenant_id = tenant_id
        return tenant_id

    async def _onboard(self, applicant: dict[str, Any]) -> uuid.UUID:
        company = applicant.get("company") or {}
        branding = applicant.get("branding") or {}
        admin = applicant.get("admin") or {}
        async with self._factory() as s:
            inst = (
                await s.execute(select(ZnunyInstance).order_by(ZnunyInstance.created_at).limit(1))
            ).scalar_one_or_none()
        if inst is None:
            raise ProvisioningError("no_znuny_instance")
        data = NewOnboarding(
            legal_name=str(company.get("legal_name") or company.get("trade_name") or ""),
            trade_name=str(company.get("trade_name") or company.get("legal_name") or ""),
            document=str(company.get("document") or ""),
            subdomain=str(applicant.get("subdomain") or ""),
            znuny_customer_id=str(applicant.get("znuny_customer_id") or ""),
            znuny_instance_id=inst.id,
            display_name=str(branding.get("display_name") or company.get("trade_name") or "Portal"),
            primary_color=str(branding.get("primary_color") or "#2563EB"),
            accent_color=str(branding.get("accent_color") or "#1E40AF"),
            support_email=branding.get("support_email"),
            logo_url=branding.get("logo_url"),
            users=[
                NewOnboardingUser(
                    email=str(admin.get("email") or ""),
                    first_name=str(admin.get("first_name") or ""),
                    last_name=str(admin.get("last_name") or ""),
                    password=str(admin.get("password") or ""),
                    role=PortalRole.admin,
                )
            ],
            created_by="checkout",
        )
        result = await OnboardingService(self._factory).onboard(data)
        return result.tenant_id
