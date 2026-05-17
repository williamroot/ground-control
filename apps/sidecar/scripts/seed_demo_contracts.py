"""Seed idempotente de contratos demo (Móveis Aurora, 6 modalidades).

Roda como **gerti_admin_user** (BYPASSRLS) via DATABASE_URL.

  cd apps/sidecar
  DATABASE_URL=postgresql+asyncpg://gerti_admin_user:...@<host>:5432/gerti \
    uv run python scripts/seed_demo_contracts.py            # seed (default)
  ... uv run python scripts/seed_demo_contracts.py --summary  # só estado
  ... uv run python scripts/seed_demo_contracts.py --reset    # apaga dados Aurora

Idempotente: cada objeto é verificado por chave natural antes do insert; a
reexecução imprime "= já existe" e nunca duplica nem viola o trigger
append-only (consumo é guardado por webhook_event_id). NÃO fecha o ciclo de
fechamento — isso é exercido pelo e2e como o motor real.

O id do tenant Aurora é impresso no stdout numa linha parseável
`TENANT_ID=<uuid>` para o controller repassar ao e2e via DEMO_TENANT_ID.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractAdjustmentRule,
    ContractCycle,
    ContractRenewalPolicy,
    Glosa,
    Tenant,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, CycleKind

INSTANCE_NAME = "Gerti Prod (znuny-dev)"
INSTANCE_BASE_URL = "https://znuny-dev.was.dev.br"
AURORA_CUSTOMER_ID = "AURORA"
START = dt.date(2026, 1, 1)
END = dt.date(2026, 12, 31)

# code -> dict of params (idempotent by (tenant_id, code))
_CONTRACTS: list[dict[str, object]] = [
    {
        "code": "AUR-HORAS-2026",
        "type": ContractType.hour_bank,
        "initial_hours": 40,
        "unit_price_brl": 180,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
    {
        "code": "AUR-CREDITO-2026",
        "type": ContractType.credit_brl,
        "initial_amount_brl": 20000,
        "unit_price_brl": 200,
        "billing_period_months": 1,
        "closing_period_months": 3,
    },
    {
        "code": "AUR-POOL-2026",
        "type": ContractType.credit_shared,
        "initial_amount_brl": 50000,
        "unit_price_brl": 220,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
    {
        "code": "AUR-PACOTE-2026",
        "type": ContractType.service_count,
        "initial_service_count": 50,
        "unit_price_brl": 150,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
    {
        "code": "AUR-FECHADO-2026",
        "type": ContractType.closed_value,
        "initial_amount_brl": 9000,
        "unit_price_brl": 9000,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
    {
        "code": "AUR-SAAS-2026",
        "type": ContractType.saas_product,
        "initial_amount_brl": 1490,
        "unit_price_brl": 1490,
        "billing_period_months": 1,
        "closing_period_months": 1,
    },
]

# Deterministic webhook ids so re-runs don't double-count (uuid5 namespace).
_NS = uuid.UUID("a0aa0a0a-0000-4000-8000-000000000001")


def _wid(tag: str) -> uuid.UUID:
    return uuid.uuid5(_NS, tag)


async def _get_or_create_instance(s: AsyncSession) -> ZnunyInstance:
    inst = (
        await s.execute(select(ZnunyInstance).where(ZnunyInstance.name == INSTANCE_NAME))
    ).scalar_one_or_none()
    if inst is not None:
        print(f"= já existe  ZnunyInstance {INSTANCE_NAME}")
        return inst
    inst = ZnunyInstance(
        name=INSTANCE_NAME,
        base_url=INSTANCE_BASE_URL,
        # vault:// refs, NOT secrets — secrets live in Vault, never here.
        db_dsn_secret_ref="vault://gerti/znuny-dev/db",  # noqa: S106
        webservice_token_secret_ref="vault://gerti/znuny-dev/webservice",  # noqa: S106
        webhook_signing_secret_ref="vault://gerti/znuny-dev/webhook",  # noqa: S106
        mode="pool",
        status="active",
    )
    s.add(inst)
    await s.flush()
    print(f"+ criado     ZnunyInstance {INSTANCE_NAME}")
    return inst


async def _get_or_create_tenant(s: AsyncSession, instance_id: uuid.UUID) -> Tenant:
    t = (
        await s.execute(select(Tenant).where(Tenant.znuny_customer_id == AURORA_CUSTOMER_ID))
    ).scalar_one_or_none()
    if t is not None:
        print(f"= já existe  Tenant {AURORA_CUSTOMER_ID}")
        return t
    t = Tenant(
        legal_name="Móveis Aurora Indústria e Comércio Ltda.",
        trade_name="Aurora Móveis",
        document="18.472.366/0001-90",
        znuny_customer_id=AURORA_CUSTOMER_ID,
        znuny_instance_id=instance_id,
        subdomain="aurora",
        status="active",
    )
    s.add(t)
    await s.flush()
    print(f"+ criado     Tenant {AURORA_CUSTOMER_ID}")
    return t


async def _get_or_create_contract(
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
    # Direct ORM insert (NOT ContractService): admin seed has no app.current_tenant
    # GUC so ContractService._current_tenant_id() would raise. Same model class.
    c = Contract(
        tenant_id=tenant_id,
        code=code,
        type=spec["type"],  # type: ignore[arg-type]
        starts_on=START,
        ends_on=END,
        initial_amount_brl=spec.get("initial_amount_brl"),  # type: ignore[arg-type]
        initial_hours=spec.get("initial_hours"),  # type: ignore[arg-type]
        initial_service_count=spec.get("initial_service_count"),  # type: ignore[arg-type]
        unit_price_brl=spec.get("unit_price_brl"),  # type: ignore[arg-type]
        billing_period_months=int(spec["billing_period_months"]),  # type: ignore[call-overload]
        closing_period_months=int(spec["closing_period_months"]),  # type: ignore[call-overload]
        created_by="seed-demo",
    )
    s.add(c)
    await s.flush()
    print(f"+ criado     Contract {code} ({c.type})")
    return c


async def _seed_credito_policies(s: AsyncSession, contract_id: uuid.UUID) -> None:
    rule = await s.get(ContractAdjustmentRule, contract_id)
    if rule is None:
        s.add(
            ContractAdjustmentRule(
                contract_id=contract_id,
                index_code="IPCA",
                cadence_months=12,
                next_run_on=dt.date(2027, 1, 1),
                cap_percent=8.00,
            )
        )
        await s.flush()
        print("+ criado     ContractAdjustmentRule AUR-CREDITO-2026 (IPCA cap 8%)")
    else:
        print("= já existe  ContractAdjustmentRule AUR-CREDITO-2026")
    pol = await s.get(ContractRenewalPolicy, contract_id)
    if pol is None:
        s.add(
            ContractRenewalPolicy(
                contract_id=contract_id,
                auto_renew=True,
                notice_days=30,
                next_review_on=dt.date(2026, 11, 30),
                renewal_term_months=12,
            )
        )
        await s.flush()
        print("+ criado     ContractRenewalPolicy AUR-CREDITO-2026 (auto-renew)")
    else:
        print("= já existe  ContractRenewalPolicy AUR-CREDITO-2026")


async def _seed_horas_cycle_and_consumption(s: AsyncSession, contract_id: uuid.UUID) -> None:
    cyc = (
        await s.execute(
            select(ContractCycle).where(
                ContractCycle.contract_id == contract_id,
                ContractCycle.kind == CycleKind.closing,
                ContractCycle.period_start == dt.date(2026, 1, 1),
            )
        )
    ).scalar_one_or_none()
    if cyc is None:
        cyc = ContractCycle(
            contract_id=contract_id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
        )
        s.add(cyc)
        await s.flush()
        print("+ criado     ContractCycle AUR-HORAS-2026 jan/2026 (closing, open)")
    else:
        print("= já existe  ContractCycle AUR-HORAS-2026 jan/2026")

    # 3 consumption events, idempotent by webhook_event_id.
    minutes = [90, 120, 150]
    first_event: ConsumptionEvent | None = None
    for i, mins in enumerate(minutes):
        wid = _wid(f"AUR-HORAS-2026:jan:{i}")
        ev = (
            await s.execute(
                select(ConsumptionEvent).where(ConsumptionEvent.webhook_event_id == wid)
            )
        ).scalar_one_or_none()
        if ev is None:
            ev = ConsumptionEvent(
                contract_id=contract_id,
                occurred_at=dt.datetime(2026, 1, 10 + i, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref=f"AUR-HORAS:jan:{i}",
                billable_minutes=mins,
                recorded_by="seed-demo",
                webhook_event_id=wid,
            )
            s.add(ev)
            await s.flush()
            print(f"+ criado     ConsumptionEvent AUR-HORAS-2026 #{i} ({mins}min)")
        else:
            print(f"= já existe  ConsumptionEvent AUR-HORAS-2026 #{i}")
        if i == 0:
            first_event = ev

    assert first_event is not None
    g = (
        await s.execute(select(Glosa).where(Glosa.consumption_event_id == first_event.id))
    ).scalar_one_or_none()
    if g is None:
        s.add(
            Glosa(
                consumption_event_id=first_event.id,
                reason="Atendimento fora de escopo - em análise",
                requested_by="seed-demo",
            )
        )
        await s.flush()
        print("+ criado     Glosa pendente sobre ConsumptionEvent #0")
    else:
        print("= já existe  Glosa sobre ConsumptionEvent #0")


async def seed(s: AsyncSession) -> uuid.UUID:
    """Idempotently seed the Aurora demo. Returns the tenant id."""
    inst = await _get_or_create_instance(s)
    tenant = await _get_or_create_tenant(s, inst.id)
    for spec in _CONTRACTS:
        c = await _get_or_create_contract(s, tenant.id, spec)
        if spec["code"] == "AUR-CREDITO-2026":
            await _seed_credito_policies(s, c.id)
        if spec["code"] == "AUR-HORAS-2026":
            await _seed_horas_cycle_and_consumption(s, c.id)
    return tenant.id


async def reset(s: AsyncSession) -> None:
    """Delete ONLY the Aurora tenant's gerti data (keeps znuny_instance)."""
    print("!! RESET: apagando TODOS os dados gerti do tenant Aurora")
    tenant = (
        await s.execute(select(Tenant).where(Tenant.znuny_customer_id == AURORA_CUSTOMER_ID))
    ).scalar_one_or_none()
    if tenant is None:
        print("= nada a fazer (tenant Aurora inexistente)")
        return
    contract_ids = (
        (await s.execute(select(Contract.id).where(Contract.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    if contract_ids:
        ev_ids = (
            (
                await s.execute(
                    select(ConsumptionEvent.id).where(
                        ConsumptionEvent.contract_id.in_(contract_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if ev_ids:
            await s.execute(delete(Glosa).where(Glosa.consumption_event_id.in_(ev_ids)))
        # consumption_event is append-only: a BEFORE trigger blocks DELETE for
        # everyone (it fires regardless of BYPASSRLS). Deleting the ledger thus
        # requires disabling the trigger, which needs table-owner/superuser
        # privileges. gerti_admin_user is BYPASSRLS but NOT the table owner
        # (migrations run as the bootstrap/superuser role), so the toggle
        # raises InsufficientPrivilege. We MUST NOT weaken append-only nor
        # leave a partial delete: fail loudly and let the transaction roll back.
        try:
            await s.execute(text("ALTER TABLE gerti.consumption_event DISABLE TRIGGER USER"))
        except Exception as exc:
            raise RuntimeError(
                "RESET abortado: não foi possível desabilitar o trigger "
                "append-only de gerti.consumption_event (precisa ser dono da "
                "tabela ou superuser). Rode o RESET com um papel proprietário "
                "da tabela (ex.: o papel que aplicou as migrations) ou limpe a "
                "base por outro meio. Append-only preservado, nada foi apagado. "
                f"Causa: {type(exc).__name__}: {exc}"
            ) from exc
        await s.execute(
            delete(ConsumptionEvent).where(ConsumptionEvent.contract_id.in_(contract_ids))
        )
        await s.execute(text("ALTER TABLE gerti.consumption_event ENABLE TRIGGER USER"))
        await s.execute(delete(ContractCycle).where(ContractCycle.contract_id.in_(contract_ids)))
        await s.execute(
            delete(ContractAdjustmentRule).where(
                ContractAdjustmentRule.contract_id.in_(contract_ids)
            )
        )
        await s.execute(
            delete(ContractRenewalPolicy).where(ContractRenewalPolicy.contract_id.in_(contract_ids))
        )
        await s.execute(delete(Contract).where(Contract.tenant_id == tenant.id))
    await s.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await s.flush()
    print(f"!! RESET concluído (tenant {tenant.id} e dependências removidos)")


async def summary(s: AsyncSession) -> None:
    tenant = (
        await s.execute(select(Tenant).where(Tenant.znuny_customer_id == AURORA_CUSTOMER_ID))
    ).scalar_one_or_none()
    if tenant is None:
        print("(sem tenant Aurora — rode o seed)")
        return
    inst = await s.get(ZnunyInstance, tenant.znuny_instance_id)
    inst_name = inst.name if inst is not None else "?"
    print()
    print(f"Tenant       : {tenant.trade_name} ({tenant.znuny_customer_id})  id={tenant.id}")
    print(f"ZnunyInstance: {inst_name}")
    print()
    header = f"{'code':<18} {'type':<14} {'status':<10} {'janela':<23} {'saldo'}"
    print(header)
    print("-" * len(header))
    contracts = (
        (
            await s.execute(
                select(Contract).where(Contract.tenant_id == tenant.id).order_by(Contract.code)
            )
        )
        .scalars()
        .all()
    )
    cons = ConsumptionService(s)
    for c in contracts:
        bal = await cons.balance(c.id)
        if bal.remaining is None:
            saldo = "—"
        else:
            saldo = f"{bal.remaining:g} {bal.kind}"
        janela = f"{c.starts_on}..{c.ends_on}"
        print(f"{c.code:<18} {c.type.value:<14} {c.status.value:<10} " f"{janela:<23} {saldo}")
    n = await s.scalar(
        select(func.count()).select_from(Contract).where(Contract.tenant_id == tenant.id)
    )
    print()
    print(f"({n} contratos)")
    print(f"TENANT_ID={tenant.id}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo Aurora (idempotente)")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--summary", action="store_true", help="só imprime o estado")
    g.add_argument("--reset", action="store_true", help="apaga dados gerti do tenant Aurora")
    args = parser.parse_args()

    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        if args.summary:
            async with factory() as s:
                await summary(s)
            return
        async with factory() as s:
            if args.reset:
                await reset(s)
                await s.commit()
            else:
                await seed(s)
                await s.commit()
        async with factory() as s:
            await summary(s)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
