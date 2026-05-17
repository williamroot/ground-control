from __future__ import annotations

from sqlalchemy import select

from gerti_sidecar.models import Contract
from gerti_sidecar.repositories.base import TenantScopedRepository


class ContractRepository(TenantScopedRepository[Contract]):
    model = Contract

    async def get_by_code(self, code: str) -> Contract | None:
        res = await self.session.execute(select(Contract).where(Contract.code == code))
        return res.scalar_one_or_none()
