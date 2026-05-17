from __future__ import annotations

import uuid

from sqlalchemy import select

from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import CycleKind, CycleStatus
from gerti_sidecar.repositories.base import TenantScopedRepository


class ContractCycleRepository(TenantScopedRepository[ContractCycle]):
    model = ContractCycle

    async def open_closing_cycles(self) -> list[ContractCycle]:
        res = await self.session.execute(
            select(ContractCycle).where(
                ContractCycle.kind == CycleKind.closing,
                ContractCycle.status == CycleStatus.open,
            )
        )
        return list(res.scalars().all())

    async def get(self, cycle_id: uuid.UUID) -> ContractCycle | None:
        return await self.session.get(ContractCycle, cycle_id)
