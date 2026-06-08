"""Fecha ciclos de fechamento vencidos, por tenant (Spec #1B).

Leitura cross-tenant (admin/BYPASSRLS) dos ciclos open+closing com period_end < hoje;
fecho sob tenant_session_scope (RLS-subject) via CycleService.close (reuso #1C).
Idempotente: um ciclo já fechado não é re-selecionado.

Nota: ContractCycle não possui coluna tenant_id — o tenant é obtido via JOIN com
Contract (Contract.tenant_id). Adaptação em relação ao plano original.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.errors import CycleError
from gerti_sidecar.models import Contract, ContractCycle
from gerti_sidecar.models.enums import CycleKind, CycleStatus


class CycleCloser:
    async def close_due_cycles(self, *, today: dt.date | None = None) -> int:
        if db.AdminSessionLocal is None:
            raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
        day = today or dt.datetime.now(dt.UTC).date()

        # ContractCycle não tem tenant_id: faz JOIN com Contract para obtê-lo.
        async with db.AdminSessionLocal() as admin:
            rows = (
                await admin.execute(
                    select(ContractCycle.id, Contract.tenant_id).join(
                        Contract, Contract.id == ContractCycle.contract_id
                    ).where(
                        ContractCycle.kind == CycleKind.closing,
                        ContractCycle.status == CycleStatus.open,
                        ContractCycle.period_end < day,
                    )
                )
            ).all()

        closed = 0
        for cycle_id, tenant_id in rows:
            async with db.tenant_session_scope(tenant_id) as s:
                try:
                    await CycleService(s).close(cycle_id)
                    closed += 1
                except CycleError:
                    # corrida/estado inesperado: pula, não derruba o lote
                    continue
        return closed
