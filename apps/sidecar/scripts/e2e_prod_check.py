"""E2E de prod: prova real do motor de contratos sob RLS.

Roda como o role NÃO privilegiado **gerti_sidecar** (sujeito a RLS) via
DATABASE_URL. O id do tenant Aurora é recebido via env DEMO_TENANT_ID
(o controller repassa a linha TENANT_ID=<uuid> emitida pelo seeder).

  cd apps/sidecar
  DATABASE_URL=postgresql+asyncpg://gerti_sidecar:...@<host>:5432/gerti \
    DEMO_TENANT_ID=<uuid> uv run python scripts/e2e_prod_check.py

Imprime PASS/FAIL por verificação e sai com código != 0 se algo falhar.
Re-runnable: cada passo evita colisões de chave natural; o passo de
reajuste lê o preço atual ANTES de aplicar e valida == round(prev*1.08, 2)
(o cap de 8% < 10% sempre clampa), de modo que múltiplas execuções
permanecem corretas.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gerti_sidecar import db
from gerti_sidecar.domain.adjustment_service import AdjustmentService
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.models import ConsumptionEvent, Contract, ContractCycle, Tenant
from gerti_sidecar.models.enums import CycleKind, CycleStatus

EXPECTED_CODES = {
    "AUR-HORAS-2026",
    "AUR-CREDITO-2026",
    "AUR-POOL-2026",
    "AUR-PACOTE-2026",
    "AUR-FECHADO-2026",
    "AUR-SAAS-2026",
}
_NS = uuid.UUID("a0aa0a0a-0000-4000-8000-000000000002")


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            self.failures += 1
        print(f"[{tag}] {name}{(' — ' + detail) if detail else ''}")


async def run_e2e(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> int:
    chk = Checker()

    # 2. Tenant scope sees its 6 contracts.
    async with db.tenant_session_scope(tenant_id, factory=factory) as s:
        codes = set((await s.execute(select(Contract.code))).scalars().all())
        chk.check(
            "tenant vê os 6 contratos AUR-*",
            EXPECTED_CODES.issubset(codes),
            f"vistos={sorted(codes)}",
        )

        horas = (
            await s.execute(select(Contract).where(Contract.code == "AUR-HORAS-2026"))
        ).scalar_one()
        credito = (
            await s.execute(select(Contract).where(Contract.code == "AUR-CREDITO-2026"))
        ).scalar_one()

        # 3. Balance: 40 - (90+120+150)/60 = 34.0 (glosa pendente NÃO reduz).
        bal = await ConsumptionService(s).balance(horas.id)
        ok3 = bal.kind == "hours" and bal.remaining is not None and abs(bal.remaining - 34.0) < 1e-9
        chk.check(
            "saldo AUR-HORAS-2026 == 34.0h (glosa pendente não reduz)",
            ok3,
            f"kind={bal.kind} remaining={bal.remaining}",
        )

        # 4. Open a Feb closing cycle, record 120min, close it.
        feb_start = dt.date(2026, 2, 1)
        cyc = (
            await s.execute(
                select(ContractCycle).where(
                    ContractCycle.contract_id == horas.id,
                    ContractCycle.kind == CycleKind.closing,
                    ContractCycle.period_start == feb_start,
                )
            )
        ).scalar_one_or_none()
        if cyc is None:
            cyc = ContractCycle(
                contract_id=horas.id,
                kind=CycleKind.closing,
                period_start=feb_start,
                period_end=dt.date(2026, 2, 28),
            )
            s.add(cyc)
            await s.flush()
        wid = uuid.uuid5(_NS, "AUR-HORAS-2026:feb:0")
        await ConsumptionService(s).record(
            RecordConsumption(
                contract_id=horas.id,
                occurred_at=dt.datetime(2026, 2, 10, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="AUR-HORAS:feb:0",
                billable_minutes=120,
                recorded_by="e2e",
                webhook_event_id=wid,
            )
        )
        if cyc.status == CycleStatus.open:
            totals = await CycleService(s).close(cyc.id)
        else:
            totals = cyc.totals or {}
        # Re-read the Feb event to confirm it got a closing_cycle_id.
        feb_ev = (
            await s.execute(
                select(ConsumptionEvent).where(ConsumptionEvent.webhook_event_id == wid)
            )
        ).scalar_one()
        await s.refresh(cyc)
        ok4 = (
            float(totals.get("consumed_minutes", -1)) == 120.0
            and cyc.status == CycleStatus.closed
            and feb_ev.closing_cycle_id == cyc.id
        )
        chk.check(
            "ciclo fev fechado: consumed_minutes=120, status=closed, evento liquidado",
            ok4,
            f"consumed={totals.get('consumed_minutes')} status={cyc.status} "
            f"closing_cycle_id={feb_ev.closing_cycle_id}",
        )

        # 5. Adjustment with cap: prev -> round(prev*1.08, 2) (cap 8% < 10%).
        prev_price = float(credito.unit_price_brl or 0)
        new_price = await AdjustmentService(s).apply_adjustment(
            credito.id, percent=10.0, on_date=dt.date(2026, 1, 1)
        )
        expected = round(prev_price * 1.08, 2)
        ok5 = abs(float(new_price) - expected) < 1e-9
        chk.check(
            "reajuste AUR-CREDITO-2026 respeita cap 8% (== round(prev*1.08,2))",
            ok5,
            f"prev={prev_price} new={new_price} expected={expected}",
        )

    # 6. Fail-closed: plain session, NO GUC -> RLS denies (0/0).
    async with factory() as s:
        t_count = await s.scalar(select(func.count()).select_from(Tenant))
        c_count = await s.scalar(select(func.count()).select_from(Contract))
        chk.check(
            "fail-closed: sem GUC, Tenant e Contract retornam 0/0",
            t_count == 0 and c_count == 0,
            f"tenant={t_count} contract={c_count}",
        )

    if chk.failures:
        print(f"E2E RESULT: {chk.failures} FAIL")
    else:
        print("E2E RESULT: ALL PASS")
    return chk.failures


async def main() -> None:
    raw = os.environ.get("DEMO_TENANT_ID")
    if not raw:
        print("ERRO: env DEMO_TENANT_ID obrigatória (uuid do tenant Aurora)")
        sys.exit(2)
    tenant_id = uuid.UUID(raw)
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        failures = await run_e2e(factory, tenant_id)
    finally:
        await engine.dispose()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
