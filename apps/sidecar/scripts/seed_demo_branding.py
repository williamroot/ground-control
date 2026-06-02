"""Seed idempotente do white-label de DOIS tenants de teste (Spec #1F-a).

Espelha scripts/seed_demo_contracts.py: argparse, create_async_engine via
DATABASE_URL, async_sessionmaker, seed(s) importável + main() fino.

Tenant 1 = Aurora (znuny_customer_id='AURORA'): JÁ existe em prod (#1C
semeou tenant + znuny_instance + 6 contratos). Aqui semeamos SÓ a linha
tenant_branding da Aurora — NÃO recriamos tenant/instância/contratos.

Tenant 2 = TechNova (znuny_customer_id='TECHNOVA', subdomain='technova'):
garante idempotentemente gerti.tenant (apontando para a MESMA única
gerti.znuny_instance — §2.1: sempre 1 Znuny), sua linha tenant_branding
(paleta/nome propositalmente DIFERENTES p/ o white-label ser óbvio) e um
conjunto PEQUENO de contratos (1 hour_bank + 1 credit_brl, cada um com
alguns ConsumptionEvent) reusando o modelo+padrão de seed_demo_contracts
(webhook ids uuid5 determinísticos → nunca viola o trigger append-only).

Check-before-insert por chave natural; reexecução imprime "= já existe".
Roda como gerti_admin_user (BYPASSRLS — atributo de role direto, init SQL
já concede; NÃO herdado via role membership). seed(s) -> (aurora_id,
technova_id).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import uuid

import seed_demo_contracts  # mesmo diretório scripts/; reuso de padrão
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    PortalUserRole,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, PortalRole

AURORA_CUSTOMER_ID = "AURORA"
TECHNOVA_CUSTOMER_ID = "TECHNOVA"
TECHNOVA_SUBDOMAIN = "technova"

# Spec #1H — papéis de demo por tenant (login sempre por e-mail). O admin vê
# contratos+valores; o help-desk cai no placeholder de tickets. Estes e-mails
# vão para o PDF de acessos; os customer_user help-desk correspondentes são
# criados no Znuny pelo seed Perl/GI (senhas de demo Aurora@Help2026 / TechNova@Help2026).
AURORA_ADMIN_LOGIN = "eduardo.salvi@auroramoveis.com.br"
AURORA_HELPDESK_LOGIN = "helpdesk@auroramoveis.com.br"
TECHNOVA_ADMIN_LOGIN = "admin.tech@technova.example"
TECHNOVA_HELPDESK_LOGIN = "suporte.ops@technova.example"

# Namespace uuid5 PRÓPRIO da TechNova (distinto do _NS do seed #1C) p/
# webhook ids determinísticos — reexecução não dobra consumo (append-only).
_TN_NS = uuid.UUID("b0bb0b0b-0000-4000-8000-000000000002")

# Contratos da TechNova: pequeno, DIFERENTE dos 6 da Aurora (códigos
# disjuntos), reusando o modelo/padrão de seed_demo_contracts.
_TN_CONTRACTS: list[dict[str, object]] = [
    {
        "code": "TNV-HORAS-2026",
        "type": ContractType.hour_bank,
        "initial_hours": 24,
        "unit_price_brl": 210,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
    {
        "code": "TNV-CREDITO-2026",
        "type": ContractType.credit_brl,
        "initial_amount_brl": 12000,
        "unit_price_brl": 230,
        "billing_period_months": 1,
        "closing_period_months": 3,
    },
]


def _tn_wid(tag: str) -> uuid.UUID:
    return uuid.uuid5(_TN_NS, tag)


async def _seed_aurora_branding(s: AsyncSession) -> uuid.UUID:
    tenant = (
        await s.execute(select(Tenant).where(Tenant.znuny_customer_id == AURORA_CUSTOMER_ID))
    ).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("Tenant Aurora inexistente — rode seed_demo_contracts.py antes.")
    existing = await s.get(TenantBranding, tenant.id)
    if existing is not None:
        print(f"= já existe  TenantBranding {AURORA_CUSTOMER_ID}")
        return tenant.id
    s.add(
        TenantBranding(
            tenant_id=tenant.id,
            display_name="Aurora Móveis",
            logo_url="https://assets.gerti.com.br/aurora/logo.svg",
            primary_color="#0EA5E9",
            accent_color="#0369A1",
            default_theme="light",
            support_email="suporte@auroramoveis.com.br",
        )
    )
    await s.flush()
    print(f"+ criado     TenantBranding {AURORA_CUSTOMER_ID} (Aurora Móveis)")
    return tenant.id


async def _seed_portal_roles(
    s: AsyncSession, tenant_id: uuid.UUID, entries: list[tuple[str, PortalRole]]
) -> None:
    """Semeia papéis (idempotente por tenant + lower(customer_login)).

    Roda como gerti_admin_user (BYPASSRLS): insere com tenant_id explícito.
    """
    for login, role in entries:
        existing = (
            await s.execute(
                select(PortalUserRole).where(
                    PortalUserRole.tenant_id == tenant_id,
                    func.lower(PortalUserRole.customer_login) == login.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"= já existe  PortalUserRole {login} ({existing.role.value})")
            continue
        s.add(PortalUserRole(tenant_id=tenant_id, customer_login=login.lower(), role=role))
        await s.flush()
        print(f"+ criado     PortalUserRole {login} -> {role.value}")


async def _get_or_create_technova_tenant(s: AsyncSession) -> Tenant:
    t = (
        await s.execute(select(Tenant).where(Tenant.znuny_customer_id == TECHNOVA_CUSTOMER_ID))
    ).scalar_one_or_none()
    if t is not None:
        print(f"= já existe  Tenant {TECHNOVA_CUSTOMER_ID}")
        return t
    # §2.1: SEMPRE exatamente 1 Znuny — TechNova aponta para a MESMA
    # instância única (a que o seed #1C criou). Não criamos uma nova.
    inst = (
        await s.execute(
            select(ZnunyInstance).where(ZnunyInstance.name == seed_demo_contracts.INSTANCE_NAME)
        )
    ).scalar_one_or_none()
    if inst is None:
        raise RuntimeError("ZnunyInstance única inexistente — rode seed_demo_contracts.py antes.")
    t = Tenant(
        legal_name="TechNova Soluções em Tecnologia Ltda.",
        trade_name="TechNova",
        document="27.911.540/0001-08",
        znuny_customer_id=TECHNOVA_CUSTOMER_ID,
        znuny_instance_id=inst.id,
        subdomain=TECHNOVA_SUBDOMAIN,
        status="active",
    )
    s.add(t)
    await s.flush()
    print(f"+ criado     Tenant {TECHNOVA_CUSTOMER_ID}")
    return t


async def _seed_technova_branding(s: AsyncSession, tenant_id: uuid.UUID) -> None:
    existing = await s.get(TenantBranding, tenant_id)
    if existing is not None:
        print(f"= já existe  TenantBranding {TECHNOVA_CUSTOMER_ID}")
        return
    # Paleta/nome propositalmente DISTINTOS da Aurora (#0EA5E9 azul) p/ o
    # white-label ser visualmente óbvio: violeta + tema escuro.
    s.add(
        TenantBranding(
            tenant_id=tenant_id,
            display_name="TechNova",
            logo_url="https://assets.gerti.com.br/technova/logo.svg",
            primary_color="#7C3AED",
            accent_color="#4C1D95",
            default_theme="dark",
            support_email="suporte@technova.example",
        )
    )
    await s.flush()
    print(f"+ criado     TenantBranding {TECHNOVA_CUSTOMER_ID} (TechNova)")


async def _get_or_create_technova_contract(
    s: AsyncSession, tenant_id: uuid.UUID, spec: dict[str, object]
) -> Contract:
    code = str(spec["code"])
    c = (
        await s.execute(
            select(Contract).where(Contract.tenant_id == tenant_id, Contract.code == code)
        )
    ).scalar_one_or_none()
    if c is not None:
        print(f"= já existe  Contract {code}")
        return c
    # Insert ORM direto (mesmo padrão de seed_demo_contracts: seed admin
    # sem GUC app.current_tenant — ContractService levantaria).
    c = Contract(
        tenant_id=tenant_id,
        code=code,
        type=spec["type"],  # type: ignore[arg-type]
        starts_on=seed_demo_contracts.START,
        ends_on=seed_demo_contracts.END,
        initial_amount_brl=spec.get("initial_amount_brl"),  # type: ignore[arg-type]
        initial_hours=spec.get("initial_hours"),  # type: ignore[arg-type]
        unit_price_brl=spec.get("unit_price_brl"),  # type: ignore[arg-type]
        billing_period_months=int(spec["billing_period_months"]),  # type: ignore[call-overload]
        closing_period_months=int(spec["closing_period_months"]),  # type: ignore[call-overload]
        created_by="seed-demo",
    )
    s.add(c)
    await s.flush()
    print(f"+ criado     Contract {code} ({c.type})")
    return c


async def _seed_technova_consumption(s: AsyncSession, contract_id: uuid.UUID, code: str) -> None:
    # 2 eventos por contrato, idempotentes por webhook_event_id uuid5
    # determinístico (jamais viola o trigger append-only ao reexecutar).
    minutes = [60, 90]
    for i, mins in enumerate(minutes):
        wid = _tn_wid(f"{code}:jan:{i}")
        ev = (
            await s.execute(
                select(ConsumptionEvent).where(ConsumptionEvent.webhook_event_id == wid)
            )
        ).scalar_one_or_none()
        if ev is not None:
            print(f"= já existe  ConsumptionEvent {code} #{i}")
            continue
        s.add(
            ConsumptionEvent(
                contract_id=contract_id,
                occurred_at=dt.datetime(2026, 1, 12 + i, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref=f"{code}:jan:{i}",
                billable_minutes=mins,
                recorded_by="seed-demo",
                webhook_event_id=wid,
            )
        )
        await s.flush()
        print(f"+ criado     ConsumptionEvent {code} #{i} ({mins}min)")


async def seed(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Idempotently seed BOTH test tenants' white-label.

    Returns (aurora_tenant_id, technova_tenant_id).
    """
    aurora_id = await _seed_aurora_branding(s)
    await _seed_portal_roles(
        s,
        aurora_id,
        [(AURORA_ADMIN_LOGIN, PortalRole.admin), (AURORA_HELPDESK_LOGIN, PortalRole.helpdesk)],
    )
    tn = await _get_or_create_technova_tenant(s)
    await _seed_technova_branding(s, tn.id)
    await _seed_portal_roles(
        s,
        tn.id,
        [(TECHNOVA_ADMIN_LOGIN, PortalRole.admin), (TECHNOVA_HELPDESK_LOGIN, PortalRole.helpdesk)],
    )
    for spec in _TN_CONTRACTS:
        c = await _get_or_create_technova_contract(s, tn.id, spec)
        await _seed_technova_consumption(s, c.id, str(spec["code"]))
    return aurora_id, tn.id


async def summary(s: AsyncSession) -> None:
    for cid in (AURORA_CUSTOMER_ID, TECHNOVA_CUSTOMER_ID):
        row = (
            await s.execute(
                select(Tenant, TenantBranding)
                .join(TenantBranding, TenantBranding.tenant_id == Tenant.id)
                .where(Tenant.znuny_customer_id == cid)
            )
        ).first()
        if row is None:
            print(f"(sem branding {cid} — rode o seed)")
            continue
        t, b = row
        n = len(
            (await s.execute(select(Contract).where(Contract.tenant_id == t.id))).scalars().all()
        )
        print()
        print(f"Tenant       : {t.trade_name} ({cid})  id={t.id}")
        print(f"display_name : {b.display_name}")
        print(f"primary      : {b.primary_color}  accent: {b.accent_color}")
        print(f"theme        : {b.default_theme}  support: {b.support_email}")
        print(f"contratos    : {n}")
        if cid == AURORA_CUSTOMER_ID:
            print(f"TENANT_ID_AURORA={t.id}")
        else:
            print(f"TENANT_ID_TECHNOVA={t.id}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed branding de 2 tenants de teste (idempotente)"
    )
    parser.add_argument("--summary", action="store_true", help="só imprime o estado")
    args = parser.parse_args()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        if args.summary:
            async with factory() as s:
                await summary(s)
            return
        async with factory() as s:
            await seed(s)
            await s.commit()
        async with factory() as s:
            await summary(s)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
