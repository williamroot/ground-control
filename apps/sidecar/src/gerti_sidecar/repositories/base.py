"""Generic tenant-scoped repository. RLS does the filtering; these are thin."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models.base import Base

T = TypeVar("T", bound=Base)


class TenantScopedRepository(Generic[T]):
    """Assumes the session was opened via db.tenant_session_scope (GUC set);
    RLS guarantees only the current tenant's rows are visible/writable."""

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[T]:
        res = await self.session.execute(select(self.model))
        return list(res.scalars().all())

    async def add(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        return obj
