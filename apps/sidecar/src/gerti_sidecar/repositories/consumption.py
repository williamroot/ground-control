from __future__ import annotations

import uuid

from sqlalchemy import select

from gerti_sidecar.models import ConsumptionEvent, Glosa
from gerti_sidecar.repositories.base import TenantScopedRepository


class ConsumptionEventRepository(TenantScopedRepository[ConsumptionEvent]):
    model = ConsumptionEvent

    async def by_webhook_event_id(self, webhook_event_id: uuid.UUID) -> ConsumptionEvent | None:
        res = await self.session.execute(
            select(ConsumptionEvent).where(ConsumptionEvent.webhook_event_id == webhook_event_id)
        )
        return res.scalar_one_or_none()

    async def for_contract(self, contract_id: uuid.UUID) -> list[ConsumptionEvent]:
        res = await self.session.execute(
            select(ConsumptionEvent).where(ConsumptionEvent.contract_id == contract_id)
        )
        return list(res.scalars().all())


class GlosaRepository(TenantScopedRepository[Glosa]):
    model = Glosa
