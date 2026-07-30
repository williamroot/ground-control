"""ServiceCatalogService — Catálogo de Serviços do portal (Spec #3 V2).

Cliente enxerga só `active=true`; console vê tudo (para poder reativar). Sem
slug/unique adicional — `id` é a chave pública usada em
`/tickets/novo?servico=<id>`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import CatalogItemNotFound
from gerti_sidecar.models import CatalogItem

DEFAULT_LIMIT = 20


class ServiceCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- portal cliente (só active=true) ---

    async def list_public(self, *, category: str | None = None) -> list[CatalogItem]:
        stmt: Select[tuple[CatalogItem]] = select(CatalogItem).where(CatalogItem.active.is_(True))
        if category:
            stmt = stmt.where(CatalogItem.category == category)
        rows = (
            (await self.session.execute(stmt.order_by(CatalogItem.sort_order, CatalogItem.name)))
            .scalars()
            .all()
        )
        return list(rows)

    async def get_public(self, item_id: uuid.UUID) -> CatalogItem:
        row = await self.session.get(CatalogItem, item_id)
        if row is None or not row.active:
            raise CatalogItemNotFound("item inexistente ou inativo")
        return row

    async def categories_public(self) -> list[tuple[str, int]]:
        rows = (
            await self.session.execute(
                select(CatalogItem.category, func.count())
                .where(CatalogItem.active.is_(True))
                .group_by(CatalogItem.category)
                .order_by(func.count().desc(), CatalogItem.category.asc())
            )
        ).all()
        return [(r[0], int(r[1])) for r in rows]

    # --- console (cross-status) ---

    async def list_admin(
        self, *, category: str | None = None, active: bool | None = None
    ) -> list[CatalogItem]:
        stmt: Select[tuple[CatalogItem]] = select(CatalogItem)
        if category:
            stmt = stmt.where(CatalogItem.category == category)
        if active is not None:
            stmt = stmt.where(CatalogItem.active.is_(active))
        rows = (
            (await self.session.execute(stmt.order_by(CatalogItem.sort_order, CatalogItem.name)))
            .scalars()
            .all()
        )
        return list(rows)

    async def get_admin(self, item_id: uuid.UUID) -> CatalogItem:
        row = await self.session.get(CatalogItem, item_id)
        if row is None:
            raise CatalogItemNotFound("item inexistente neste tenant")
        return row

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        category: str,
        description: str | None,
        sla_hours: int | None,
        icon: str,
        znuny_queue: str | None,
        znuny_service: str | None,
        default_priority: str | None,
        active: bool,
        sort_order: int,
    ) -> CatalogItem:
        item = CatalogItem(
            tenant_id=tenant_id,
            name=name,
            category=category,
            description=description,
            sla_hours=sla_hours,
            icon=icon,
            znuny_queue=znuny_queue,
            znuny_service=znuny_service,
            default_priority=default_priority,
            active=active,
            sort_order=sort_order,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def update(
        self,
        item_id: uuid.UUID,
        *,
        name: str,
        category: str,
        description: str | None,
        sla_hours: int | None,
        icon: str,
        znuny_queue: str | None,
        znuny_service: str | None,
        default_priority: str | None,
        active: bool,
        sort_order: int,
    ) -> CatalogItem:
        item = await self.get_admin(item_id)
        item.name = name
        item.category = category
        item.description = description
        item.sla_hours = sla_hours
        item.icon = icon
        item.znuny_queue = znuny_queue
        item.znuny_service = znuny_service
        item.default_priority = default_priority
        item.active = active
        item.sort_order = sort_order
        await self.session.flush()
        # `updated_at` (onupdate=func.now()) fica expirado após o UPDATE; sem o
        # refresh, o acesso síncrono no router (Pydantic model_dump) dispara um
        # lazy-load fora do greenlet do AsyncSession -> MissingGreenlet.
        await self.session.refresh(item)
        return item

    async def delete(self, item_id: uuid.UUID) -> None:
        item = await self.get_admin(item_id)
        await self.session.delete(item)
        await self.session.flush()
